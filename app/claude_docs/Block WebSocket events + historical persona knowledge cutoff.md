# TASK: Block/unblock WebSocket events + historical persona knowledge cutoff

## Scope

**Backend only.** This doc covers server-side event contracts, emit
triggers, and one new socket handler — nothing about how any client
consumes or renders these events. Two independent features, bundled since
both touch `socketio_server.py` and `PersonaSession`/`Brain` in adjacent
ways:

1. Two structural WebSocket events (`persona_blocked`, `persona_unblocked`)
   marking the block state transitions, plus one new handler
   (`check_unblock_status`) for callers to poll unblock status on demand.
2. A knowledge-cutoff mechanism for historical personas (e.g. Winston
   Churchill), so they correctly cannot know about anything after a fixed
   date — including within their own domain of expertise — while reacting
   with genuine in-character eagerness/curiosity rather than flat refusal.

Both assume `persona_sessions`, `PersonaSession.load()`/`save()`, and the
auto-expiring block mechanism (`blocked_until`, lazy unblock-on-load) are
already implemented per earlier tasks. If any of that has drifted from what's
described here, verify against actual current files first (see reminder at
bottom).

---

## PART A — Block / unblock WebSocket events

### A1. `persona_blocked` event — fires only on the transition into blocked

Needs a transient, turn-local flag on `PersonaSession` — same pattern
already used for `last_turn_context`/`curiosity_zone` (reset at the top of
each turn, read once by the orchestrating layer, never persisted):

```python
# In PersonaSession, alongside other turn-local fields:
self.just_blocked: bool = False  # reset False at top of update(), set True
                                   # only at the exact moment is_blocked flips
                                   # False -> True this turn
```

Set `just_blocked = True` at both existing block-trigger sites:
- The arousal-threshold check (currently in `compile_prompt()`, sets
  `blocked_until`/`block_reason`) — add `self.just_blocked = True` there,
  guarded so it only fires if `is_blocked` was `False` before this check
  (not on a turn where it's already blocked and this just re-confirms it).
- `register_violation()`'s block-threshold branch — same guard, same flag.

### A2. Emit site — orchestrating layer, not `PersonaSession` itself

`PersonaSession` stays fully I/O-free, per its existing design contract —
the actual `socketio.emit(...)` call belongs in whatever function in
`socketio_server.py`/`Brain.build()`'s caller already handles sending the
regular AI reply back to the room. After the build/save cycle completes for
a turn:

```
IF persona_session.just_blocked:
    EMIT 'persona_blocked' TO room (same room as receive_message uses)
        payload = {
            "persona_session_id": persona_session.session_id,
            "block_reason": persona_session.block_reason,
            "blocked_until": persona_session.blocked_until.isoformat(),
        }
    // Emitted ALONGSIDE the normal receive_message emit for this turn's
    // canned refusal reply, not instead of it — the chat message and the
    // structural event are two separate signals serving two separate
    // frontend needs (message bubble vs. UI state change).
```

### A3. `check_unblock_status` — on-demand handler, NOT a server-side scheduled task

Deliberately a request/response handler rather than a background-task/
scheduled-push approach: this stack has no existing job scheduler, and a
`blocked_until`-based sleeping task would not survive a server restart and
would need cross-instance message routing (e.g. a Socket.IO Redis adapter)
to work correctly under multiple server processes — infrastructure this
task does not assume exists. This handler is called on demand and simply
answers "is this session still blocked, right now" — no timing/polling
logic of any kind belongs on the backend side of this.

```
ON 'check_unblock_status' event (payload: {persona_session_id}):
    session = PersonaSession.load(ai_persona_id, human_persona_id)
    // Reuses the EXISTING lazy unblock-on-load logic entirely — no new
    // unblock logic is written for this task. load() already flips
    // is_blocked False and runs decay if blocked_until has passed.

    IF NOT session.is_blocked:
        EMIT 'persona_unblocked' TO the requesting client (not broadcast —
            this is a private status check, not a room-wide event)
            payload = {"persona_session_id": session.session_id}
    // ELSE: still blocked — no emit, no payload, nothing changed.
```

No `save()` call needed here if `load()` alone determines the answer and
nothing about this specific request should count as a "turn" — confirm
against how `load()` is currently implemented whether calling it here has
any side effects that would need guarding (e.g. if `load()` itself always
writes something on every call, that may need a read-only variant for this
specific handler).

---

## PART B — Historical persona knowledge cutoff

### B1. `StructuredTraits` — new static field

```python
class StructuredTraits(BaseModel):
    # ...existing fields unchanged...
    knowledge_cutoff_date: Optional[str] = None  # ISO date string, e.g.
        # "1965-01-24" for Churchill. None for every non-historical persona
        # — this feature should add zero prompt cost or behavior change for
        # a contemporary persona like the existing Trump persona.
```

### B2. `TopicDetectionResponse` — new conditional field

```python
class TopicDetectionResponse(BaseModel):
    topic_domain: Topic
    subject_label: str
    is_same_subject: bool
    requires_post_cutoff_knowledge: bool = False
    # Only meaningfully populated when the persona has a
    # knowledge_cutoff_date set — see B3 for the conditional prompt
    # inclusion. True if the message references, requires, or implicitly
    # assumes knowledge of any real-world event, technology, person, or
    # fact that postdates that persona's cutoff — REGARDLESS of which
    # topic_domain it also resolves to. A question can be squarely EXPERT
    # (e.g. politics, for Churchill) and still require post-cutoff
    # knowledge (e.g. asking about a living politician who took office
    # decades after his death).
```

### B3. `_detect_topic()` prompt — conditional section

```
IF persona.knowledge_cutoff_date IS NOT NULL:
    ADD to the topic-detection system prompt:
        "This persona's knowledge and life ends on {knowledge_cutoff_date}.
        Determine whether this message references, requires, or assumes
        knowledge of anything — technology, real-world events, real people,
        or the current status of anything — that occurred or came to exist
        AFTER that date, even if the general subject (e.g. politics) is
        squarely within their historical expertise. Example: 'What do you
        think of TikTok?' requires post-cutoff knowledge even though social
        commentary was their domain. 'What did you think of the Yalta
        Conference?' does not, since that predates the cutoff. Set
        requires_post_cutoff_knowledge accordingly."
// Only included conditionally — do not add this section (or reasoning
// overhead) to the prompt for any persona without a cutoff date.
```

### B4. `compile_prompt()` — override takes priority over normal topic gating

This must short-circuit BEFORE the existing `EXPERT`/`GENERAL_KNOWLEDGE_*`/
`NOT_AN_EXPERT` decision tree, not sit as one more branch inside it —
`requires_post_cutoff_knowledge` can be true regardless of what
`topic_domain` also resolved to.

```
IF requires_post_cutoff_knowledge AND has_emotional_capacity():
    # Eager, forward-leaning framing — NOT bewildered dismissal. A
    # historically opinionated figure (the Churchill case this was
    # designed against) would want the answer immediately, not shrug at
    # not knowing.
    knowledge_str = (
        "This is something entirely beyond your lifetime — you have "
        "absolutely no way of knowing it. But don't just react with "
        "confusion or dismiss it — you are genuinely eager to find out. "
        "Ask the user directly, with real urgency or interest, to tell "
        "you. Do not pretend to know or guess at an answer."
    )
ELIF requires_post_cutoff_knowledge:  # capacity absent — heated/worn down
    # Same core restriction, but without the eager-question framing —
    # matches how every other capacity-gated directive in this system
    # already degrades (banter, vulnerability, curiosity) when arousal/
    # patience are outside the has_emotional_capacity() window.
    knowledge_str = (
        "This is something entirely beyond your lifetime — you have no "
        "way of knowing it. Say so plainly, briefly, without elaboration."
    )
ELSE:
    // existing decision tree, completely unchanged
```

**Second-turn behavior — explicit test case, not just an implementation
note.** Once the user answers the eager question (e.g. "Keir Starmer"), the
NEXT turn must let the persona genuinely react in-character to that new
information (praise, horror, bewilderment — whatever fits) rather than
re-triggering the same "I cannot know this" wall, since the user's answer is
now what's being discussed, not a request for the persona to produce
forbidden knowledge itself. Verify `_detect_topic()` classifies the
follow-up turn correctly — the user's own statement ("His name is Keir
Starmer") should NOT itself flag `requires_post_cutoff_knowledge=True` just
because the subject matter does; the classifier needs to distinguish "the
PERSONA is being asked to know this" from "the USER is telling the persona
this."

### B5. New `ANACHRONISTIC` curiosity zone — dedicated, not reused Apathy

Deliberately NOT folded into the existing `APATHY` zone. Apathy's framing
(disinterest, ego-driven bridging) is the wrong emotional register for
"something from decades in my future" — that's closer to maximal
information-gap territory, which is what `CURIOSITY`'s peak already models,
just more intensely.

```python
class CuriosityZone(str, Enum):
    APATHY = "apathy"
    CURIOSITY = "curiosity"
    BOREDOM = "boredom"
    ROUTED_AROUND = "routed_around"
    ANACHRONISTIC = "anachronistic"  # NEW
```

```
FUNCTION classify_curiosity_zone(topic, requires_post_cutoff_knowledge) -> CuriosityZone:
    IF requires_post_cutoff_knowledge:
        RETURN ANACHRONISTIC   // checked FIRST — overrides normal zone
                                 // resolution the same way B4 overrides
                                 // normal knowledge-gating
    // ...existing logic unchanged for everything else...
```

`curiosity_delta` needs an `ANACHRONISTIC` branch with its OWN (likely
higher) base weight than `CURIOSITY`'s peak — this is arguably the single
largest information-gap this system can represent, and should accrue
accordingly:

```
ELIF zone == ANACHRONISTIC:
    // No repetition-fatigue decay applied here unlike CURIOSITY — every
    // distinct post-cutoff topic is presumably equally novel to a persona
    // who has never encountered ANY of it, so topic_repeat_streak isn't a
    // meaningful signal in this zone the way it is for ordinary expertise
    // topics. Confirm this assumption holds in testing; revisit if a user
    // hammers the same anachronistic subject repeatedly and it should
    // plausibly still get old.
    stimulation = novelty_factor * (zone_base * 1.5)  // higher weight than
                                                          // CURIOSITY's peak
```

Capacity gating in `compile_prompt()`'s curiosity-directive selection
(separate from B4's knowledge-gating override) should still apply as normal
— a heated/worn-down persona doesn't get the eager-question framing even if
`self.curiosity` is high from this zone, consistent with every other
capacity-gated directive already in the system.

---

## Test plan

1. **Block event fires once, not repeatedly.** Trigger a block, confirm
   `persona_blocked` emits on that exact turn. Send a second message while
   still blocked (hard-gate short-circuit fires), confirm `persona_blocked`
   does NOT emit again — `just_blocked` should be `False` on that turn.
2. **Unblock check — true unblock case.** Set `blocked_until` in the past,
   fire `check_unblock_status`, confirm `persona_unblocked` emits to the
   requesting client only (not broadcast to the room).
3. **Unblock check — premature case.** Set `blocked_until` still in the
   future, fire `check_unblock_status`, confirm NOTHING emits.
4. **Cutoff — in-domain but post-cutoff.** Historical persona with
   `knowledge_cutoff_date` set, expertise includes Politics, ask about a
   living current politician. Confirm `requires_post_cutoff_knowledge=True`
   despite `EXPERT`-eligible topic, and the eager-question directive fires
   (not the normal `EXPERT` directive).
5. **Cutoff — pre-cutoff historical question.** Same persona, ask about a
   documented pre-cutoff historical event within their expertise. Confirm
   `requires_post_cutoff_knowledge=False`, normal `EXPERT` directive fires
   unchanged.
6. **Cutoff — capacity-gated degradation.** Same post-cutoff question, but
   with arousal artificially pushed above the capacity ceiling first.
   Confirm the flatter "no way of knowing, briefly" directive fires instead
   of the eager-question version.
7. **Second-turn reaction — the two-turn test explicitly called out in B4.**
   Turn 1: ask persona about a post-cutoff figure, confirm eager-question
   response. Turn 2: user supplies the answer as a statement. Confirm turn 2
   does NOT re-trigger `requires_post_cutoff_knowledge=True` for the user's
   own statement, and the persona genuinely reacts in-character to the new
   information rather than repeating the "I cannot know this" wall.
8. **Non-historical personas unaffected.** Run existing tests against the
   Trump persona (no `knowledge_cutoff_date`), confirm zero behavior change
   — `requires_post_cutoff_knowledge` should never be `True` and the
   conditional prompt section should never be included for this persona.

---

## Reminder before implementing

This doc assumes `persona_sessions`, `PersonaSession.load()`/`save()`, and
the auto-expiring block mechanism already exist exactly as designed in
earlier tasks. A prior task doc in this same series was caught describing a
fix that had ALREADY been implemented, because the doc was written from
design-discussion memory rather than cross-checked against the actual
current files. Before implementing anything in this doc: read the current,
real state of `persona_session.py`, `emotion_engine.py`, `schemas.py`, and
`socketio_server.py` first, and flag anything here that doesn't match what's
actually there rather than assuming this doc is authoritative over the real
code.