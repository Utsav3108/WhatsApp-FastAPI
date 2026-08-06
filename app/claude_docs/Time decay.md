# TASK: Wall-clock time decay + auto-expiring block (max 1 hour, configurable)

## Scope

Adds real-world elapsed-time decay to arousal/mood/patience between messages
(not just turn-based deltas, which already exist and are unaffected by this
task), and converts the current **permanent** block (`is_blocked=True`, no
expiry) into an **auto-expiring** block with a configurable maximum duration,
currently 1 hour.

This builds on top of `persona_sessions` (from the earlier persistence task)
and `PersonaSession.load()`/`save()`. If that work hasn't landed yet, this
task depends on it — confirm `persona_sessions` table and the `load()`/`save()`
boundary methods exist before starting.

---

## IMPORTANT — schema conflict found during design, resolved below, confirm before implementing

Earlier persistence design decided the hard-gate short-circuit (blocked
session, `Brain.build()` step 1) should still call `save()` to bump
`updated_at`, so a blocked session stays correctly ranked for "most-recent-
active" fork selection even while someone keeps messaging it.

This feature needs the OPPOSITE for a different field: the decay
calculation's elapsed-time anchor must stay frozen at the moment blocking
began, NOT get reset every time someone pokes a blocked session — otherwise
`elapsed_hours` never accumulates and the block effectively never cools down
regardless of configured duration.

**Resolution: two separate timestamp fields, not one, doing two different
jobs:**
- `updated_at` (already exists) — bumped on EVERY `save()` call, including
  the hard-gate/blocked path. Used ONLY for fork "most-recent-active"
  ordering. Unchanged from current design.
- `last_emotional_update_at` (NEW) — bumped ONLY when `update()` actually
  runs and mutates arousal/patience/mood/curiosity (i.e., NOT on the
  hard-gate short-circuit, NOT while blocked). This is what decay
  calculations read elapsed time against.

If this split feels like overkill and you'd rather simplify, the alternative
is dropping the earlier "still save() on hard-gate" decision instead —
but that would mean a poked-but-blocked session stops climbing fork-recency
ranking, which was the whole point of that earlier decision. Recommend
keeping both fields rather than reverting the earlier choice.

---

## PHASE 1 — `app/brain/emotion_engine.py` — new pure decay functions

```python
FUNCTION half_life_hours(self_regulation: float, threat_sensitivity: float) -> float:
    RETURN 24.0 * (self_regulation / max(threat_sensitivity, 1.0))
    // High self_regulation + low threat_sensitivity -> fast cooldown
    // (secure, even-tempered persona lets things go quickly).
    // Low self_regulation + high threat_sensitivity -> slow cooldown
    // (a grudge-holder still simmering the next day with zero new
    // provocation). Same two traits already drive in-conversation arousal
    // rise and patience drain — this is a third, distinct job for them:
    // recovery rate, not reactivity or drain rate.

FUNCTION time_cooldown_delta(arousal: float, mood: float, patience: float,
                             self_regulation: float, threat_sensitivity: float,
                             baseline_security: float, elapsed_hours: float) -> dict:
    // Pure function — no side effects, no DB awareness, matches every
    // other EmotionEngine method's contract.
    IF elapsed_hours <= 0:
        RETURN {}  // no time passed, nothing to compute

    half_life = half_life_hours(self_regulation, threat_sensitivity)
    cooldown = 1.0 - exp(-elapsed_hours / half_life)

    new_arousal = arousal - (arousal * cooldown)              // relaxes toward 0
    new_mood = mood * (1.0 - cooldown)                          // drifts toward 0 (neutral)
    new_patience = patience + (100.0 - patience) * cooldown * (baseline_security / 100.0)
                                                                  // regenerates toward 100,
                                                                  // rate gated by security

    RETURN {
        "arousal": new_arousal - arousal,     // delta, not absolute — consistent with
        "mood": new_mood - mood,               // every other *_delta method returning
        "patience": new_patience - patience,   // deltas for _apply() to consume
    }
    // rapport is DELIBERATELY excluded — it's durable relationship memory,
    // not mood, and does not decay with time. Do not add a rapport term here.
```

Call site: `PersonaSession._apply()` already exists and can consume this
delta dict unchanged, since it already knows how to apply arbitrary
arousal/mood/patience deltas.

---

## PHASE 2 — `persona_sessions` schema additions

Two new columns, added to the table from the earlier persistence task:

```sql
ALTER TABLE persona_sessions ADD COLUMN blocked_until TIMESTAMP WITH TIME ZONE NULL;
-- NULL = not blocked. Non-null timestamp = blocked until this moment.
-- Replaces the current permanent is_blocked=True-forever behavior.

ALTER TABLE persona_sessions ADD COLUMN last_emotional_update_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now();
-- Bumped ONLY when update() actually mutates state — NOT on the hard-gate
-- short-circuit, NOT while blocked. This is the decay-calculation anchor,
-- deliberately separate from updated_at (which serves fork-ordering only —
-- see conflict resolution above).
```

`is_blocked` (existing boolean column) and `block_reason` (existing string
column) are KEPT, not replaced — `is_blocked` becomes a derived/cached
convenience flag (`blocked_until IS NOT NULL AND blocked_until > now()`),
`block_reason` still records *why* (`'arousal_threshold'` or
`'repeated_content_violations'`), unchanged.

---

## PHASE 3 — Configurable block duration constant

```python
# app/brain/emotion_engine.py or persona_session.py — single, easy-to-find
# constant, per the requirement that this stays trivially adjustable:
BLOCK_DURATION_HOURS: float = 1.0  # MAXIMUM block length. Change this single
                                     # value to adjust — no other code should
                                     # need to change when this number does.
```

Both existing block triggers switch from setting a permanent flag to setting
an expiry:

```python
# CURRENT (arousal-threshold block, in compile_prompt()):
#   self.is_blocked = True
#   self.block_reason = "arousal_threshold"
# NEW:
self.blocked_until = now() + timedelta(hours=BLOCK_DURATION_HOURS)
self.block_reason = "arousal_threshold"

# CURRENT (register_violation(), violation-count block):
#   self.is_blocked = True
#   self.block_reason = "repeated_content_violations"
# NEW:
self.blocked_until = now() + timedelta(hours=BLOCK_DURATION_HOURS)
self.block_reason = "repeated_content_violations"
```

**This is a real behavior change from current live code, not just an
addition** — confirm before implementing that both trigger paths (arousal
AND violation count) should get the same auto-expiry treatment, rather than
only one of them. Doc assumes both; flag if you want them to differ (e.g.
violations could reasonably warrant a longer or non-expiring block than a
simple arousal spike — this is a product decision, not something to assume
silently).

---

## PHASE 4 — `PersonaSession.load()` — lazy decay + lazy unblock, in that order

```
CLASSMETHOD load(ai_persona_id, human_persona_id) -> PersonaSession:
    row = SELECT most-recent-active persona_sessions row  // unchanged from earlier design
    ai_persona = get_persona(ai_persona_id)  // cached, unchanged
    human_persona = get_persona(human_persona_id)  // unchanged

    session = PersonaSession(...)  // construct as before
    session.session_id = row.id if row else None

    IF row IS NOT NULL:
        // hydrate all existing fields as before (arousal, patience, mood,
        // rapport, curiosity, last_subject, topic_repeat_streak, turn_count,
        // violation_count) ...

        now = current_utc_time()

        // --- LAZY UNBLOCK CHECK, runs first ---
        IF row.blocked_until IS NOT NULL AND row.blocked_until <= now:
            session.blocked_until = None
            session.is_blocked = False
            // block_reason intentionally left as-is (historical record of
            // why it WAS blocked) — clear it too if you'd rather it read as
            // fully reset; flagging as a minor style choice, not a hard
            // requirement either way.
        ELIF row.blocked_until IS NOT NULL:
            // still genuinely blocked — do NOT run decay below, return
            // early. Frozen exactly as designed: no partial cooldown while
            // still inside the block window.
            session.blocked_until = row.blocked_until
            session.is_blocked = True
            session.arousal = row.arousal  // untouched, frozen
            session.patience = row.patience
            session.mood = row.mood
            RETURN session  // Brain.build()'s hard gate handles the rest

        // --- DECAY, only reached if NOT currently blocked ---
        elapsed_hours = (now - row.last_emotional_update_at) / 3600.0
        deltas = EmotionEngine.time_cooldown_delta(
            arousal=row.arousal, mood=row.mood, patience=row.patience,
            self_regulation=session.self_regulation,
            threat_sensitivity=session.threat_sensitivity,
            baseline_security=session.baseline_security,
            elapsed_hours=elapsed_hours,
        )
        session._apply(deltas)  // reuses the existing _apply() method unchanged
        // rapport, curiosity, violation_count, turn_count, topic_repeat_streak,
        // last_subject — all hydrated as-is, untouched by decay, exactly per
        // the earlier design (rapport is durable; the others aren't time-based).

    RETURN session
```

**Key ordering point**: decay must run and complete BEFORE `Brain.build()`
calls `update()` for the current turn's message — so the very first reply
after an auto-unblock (or after any real gap in conversation) is already
computed against the decayed state, not the frozen pre-decay values. This
matches the "user never sees a reply generated at the frozen extreme"
behavior confirmed in design discussion.

---

## PHASE 5 — `PersonaSession.save()` — write both timestamps correctly

```
METHOD save():
    now = current_utc_time()
    IF an update() actually ran this turn (i.e., this is NOT the hard-gate
    short-circuit path):
        self.last_emotional_update_at = now
    // updated_at is bumped automatically via onupdate=func.now() regardless
    // (unchanged from earlier design) — it fires on every save() call,
    // hard-gate path included.

    UPDATE/INSERT persona_sessions SET
        arousal=..., patience=..., mood=..., rapport=..., curiosity=...,
        last_subject=..., topic_repeat_streak=..., turn_count=...,
        violation_count=..., is_blocked=..., block_reason=...,
        blocked_until=..., last_emotional_update_at=...
    WHERE id = self.session_id
```

**Practical implication for `Brain.build()`'s call site**: the hard-gate
short-circuit (persona already blocked, returns canned refusal) still calls
`save()` per the earlier decision — but that call must NOT touch
`last_emotional_update_at`, only `updated_at` (via the DB's automatic
`onupdate`). Whichever code path implements `save()` needs a way to
distinguish "just bump updated_at" from "bump both" — simplest is an
explicit parameter, e.g. `session.save(state_changed=False)` on the hard-gate
path vs. the default `True` everywhere else.

---

## Test plan

1. **Basic decay math** — construct a session with known traits, set
   `arousal=90`, `last_emotional_update_at` 10 hours in the past, call
   `load()`, confirm the resulting arousal matches `half_life_hours()` +
   `time_cooldown_delta()` computed by hand, not just "some lower number."
2. **Rapport never decays** — same setup, confirm `rapport` is bit-for-bit
   unchanged regardless of elapsed time.
3. **Frozen-while-blocked** — set `blocked_until` 30 minutes in the future,
   set `arousal=100`, call `load()`, confirm arousal is returned UNCHANGED
   (still 100, no partial decay) and `is_blocked=True`.
4. **Auto-unblock + immediate decay in the same call** — set `blocked_until`
   1 second in the past, `last_emotional_update_at` matching whenever the
   block began (e.g. 1 hour + a few minutes ago), call `load()`, confirm
   BOTH: `is_blocked` flips to `False`, AND arousal reflects decay computed
   over the full elapsed duration since blocking began — not zero, not a
   fresh reset to baseline.
5. **Hard-gate path does not corrupt the decay anchor** — send a message to
   a currently-blocked session (still within the block window), confirm
   `updated_at` changes but `last_emotional_update_at` does NOT, confirm the
   session still sorts correctly as "most-recent-active" for fork selection
   despite being blocked.
6. **Both block triggers use the new expiry mechanism** — trigger a block via
   arousal threshold once, via violation count in a separate test, confirm
   both set `blocked_until` correctly using the current `BLOCK_DURATION_HOURS`
   constant rather than one of them still setting a permanent flag.
7. **Changing `BLOCK_DURATION_HOURS`** — confirm it's a single constant whose
   value change doesn't require touching any other line of code to take
   effect on the next newly-triggered block.