# Persona Emotion Engine — Design Spec & Pending Work

This doc captures the current working state of `persona_session.py` +
`emotion_engine.py`, and specifies work that's been designed but not yet
implemented. Intended as context for an implementation session (e.g. Claude
Code) — it describes *intent*, not just the diff.

---

## 1. Architecture recap

Two-layer split:

- **Traits** (`threat_sensitivity`, `self_regulation`, `novelty_drive`,
  `baseline_security`, `empathic_resonance`) — fixed per persona, set once at
  construction, never mutated. Parameterize every formula below; they are
  rate constants, not values that move.
- **State** (`arousal`, `patience`, `mood`, `rapport`, `curiosity`) — mutable,
  per-session, updated every turn via `EmotionEngine`'s pure delta functions
  and applied through `PersonaSession._apply()`.

`EmotionEngine` is a stateless calculator: every method takes explicit
primitive inputs and returns a delta dict, with no reference to
`PersonaSession`. This is deliberate — keeps every formula independently
testable and tunable without needing a live session object.

`PersonaSession.update(context)` runs once per turn: classifies the turn
into exactly one state-math branch (compliment / banter / hostility /
apology / competition / vulnerable / conversation-drain), then runs the
curiosity engine and the anger-mood coupling pass, in that order.

`PersonaSession.compile_prompt(context)` translates the numeric state into
an English directive block injected into the persona's system prompt. This
function has one side effect (`self.is_blocked = True` on arousal-threshold
breach) — known, accepted, not yet worth abstracting away for a
single-session prototype.

---

## 2. Current working formulas (as of last verified state)

These are settled and working — verified against real conversation logs,
values traced by hand against the formulas and confirmed correct to
rounding. Do not change without a specific reason; if modifying, re-verify
against a fresh log the same way.

```
arousal_0    = max(0, 30 - baseline_security/4)
patience_0   = min(100, 40 + self_regulation/2)
mood_0       = 0
rapport_0    = 0
curiosity_0  = 0
```

**Compliment / warm / excitement tone** → `compliment_delta`:
mood += intensity×0.25, rapport += intensity×0.15, arousal -= intensity×0.1,
patience += intensity×0.1.

**Genuine hostility** (`Intent.INSULT`, `Intent.HARMFUL_INTENT`, or
`Tone.AGGRESSIVE` — evaluated regardless of capacity) → `hostility_delta`:
tone_multiplier = 1.5 if AGGRESSIVE/SARCASTIC else 1.0.
arousal += (threat_sensitivity/100) × intensity × tone_multiplier.
patience -= (intensity × tone_multiplier) / self_regulation.
mood -= intensity×0.2.

**Playful sarcasm/banter** (`Intent.SARCASM` or `Tone.SARCASTIC`, only when
NOT genuine hostility AND `has_emotional_capacity()` is true) →
`banter_delta`: lighter version of hostility (0.3x weighting on arousal/
patience cost) plus a mood boost (intensity×0.1) — a good roast is fun, not
a wound, but capacity-gated: the same message reads as hostile instead once
patience/arousal cross the capacity thresholds.

**Apology** → `apology_delta`: anger_modifier = 0.5 if arousal≥70 else 1.0
(apologies land weaker once already furious). forgiveness_rate =
empathic_resonance × (baseline_security/100) × anger_modifier.
arousal -= (forgiveness_rate/100) × intensity. patience += intensity×0.1.

**Competition** → `competition_delta`: arousal += (threat_sensitivity/100) ×
intensity × 0.4 (much gentler than real hostility — stimulating, not
threatening). mood += intensity×0.05.

**Vulnerable tone**, capacity-gated → `vulnerable_delta`: if NOT
`has_emotional_capacity()`, only a small patience cost (intensity×0.05) —
dysregulation crowds out empathic bandwidth, being confronted with someone
else's difficulty while heated reads as one more demand, not an invitation.
If capacity present: mood -= intensity×0.1×empathy_factor (catching some of
their difficulty), rapport += intensity×0.2×empathy_factor, arousal -=
intensity×0.05×empathy_factor.

**Conversation/Ask** → `conversation_drain`: base_drain = 3.0 -
(self_regulation/50). rapport_discount = rapport/100. drain = max(0,
base_drain - rapport_discount). patience -= drain. mood += intensity×0.05.
(Temperament sets how fast this persona tires, period; rapport discounts
that cost for a specific trusted relationship — two independent axes.)

**Content violation** (harmful/sexual topic short-circuit in `Brain`) →
`content_violation_delta`: patience is capped DOWN to ≤50 (floor/ceiling,
not flat overwrite — doesn't let an already-angrier persona off easy).
arousal is floored UP to ≥50. Escalates to a hard, permanent
`is_blocked=True` after `VIOLATION_BLOCK_THRESHOLD` (default 2) violations.
When blocked this way, `Brain.build()` must skip the Gemini classification
call entirely on all subsequent turns (verified working in testing).

**Anger–mood coupling** (`anger_mood_cap`) — applied every turn, to real
state, not just display: `mood = min(mood, 0) if arousal > 70 else mood`.
Negative-affect dominance: genuine anger crowds out positive mood regardless
of what else landed that turn. This must run on the *actual* mood value,
not just change the displayed string — otherwise mood silently stays
inflated underneath an angry directive and snaps back the instant arousal
dips.

**Greeting / Goodbye** — intentional no-op on state. Repetition callouts
("user keeps saying hi") are handled entirely via a response-style
instruction downstream, not via persona state — confirmed working, no
`greeting_streak` tracking needed in this file.

---

## 3. Topic comprehension filter — current three/four-way split

`Topic` enum includes a GK disambiguation split, resolved by the classifier
prompt (which is given `expertise_topics` as context — see note below):

- `Topic.GENERAL_KNOWLEDGE_UNFAVORITE` — casual-phrased question on a
  subject outside `expertise_topics` (e.g. "explain mitochondria"). **Hard
  wall**: directive explicitly forbids leaking even partial real content,
  must dismiss and redirect. This is the fix for a confirmed bug where a
  GK-phrased question on an unfavorited subject could get reclassified one
  turn later (via a topic-vague follow-up message) and leak real content
  that had just been correctly denied — see Known Issues below, not fully
  closed yet.
- `Topic.GENERAL_KNOWLEDGE_FAVORITE` — casual-phrased question that touches
  a subject in `expertise_topics`. Softer directive: knows a bit, keeps it
  casual/enthusiastic, no deep technical detail.
- `Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL` — about the persona's own life/
  journey, not gated by expertise at all.
- topic `in expertise_topics` (non-GK, i.e. asked in a deep/technical
  register) → "you are an expert in this field."
- `Topic.UNIDENTIFIED` (gibberish) → no topic constraint at all.
- everything else → "no knowledge of what user is saying."

**Important**: the classifier's system prompt must be given
`expertise_topics` as explicit context (not just the fixed enum
descriptions) so it can correctly tell FAVORITE from UNFAVORITE relative to
*this* persona. `expertise_topics` is now the single source of truth for
both the compile_prompt gate and the classifier's disambiguation — there is
no separate `favorite_topics` list.

---

## 4. Known open issue — topic continuity across ambiguous turns

**Confirmed bug pattern**: A subject correctly denied on turn N
(`GENERAL_KNOWLEDGE_UNFAVORITE`) can get reclassified on turn N+1 if the
user's message is topic-vague (e.g. a bragging non-sequitur with no
explicit subject noun) — because the classifier has no hard anchor to what
was actually being discussed.

The classifier already receives the raw last-10-message history
(`previous_messages`, injected verbatim into the system prompt in
`MessageAnalysis._generate_message_metadata`, `app/brain/message_analysis.py`)
specifically so Gemini 2.5 Flash can read conversational context when
judging intent/tone/topic — that part is deliberate and working. What it
does *not* get is the actual `topic_domain` label the engine assigned last
turn as a structured fact, so a topic-vague follow-up has nothing forcing
it to stay classified the same way. (`PersonaSession.summary` is unrelated
here — it's dead: written once, and that write is commented out in
`app/gemini.py`, with zero reads anywhere in the codebase.)

**Not yet implemented fix** — pass the actual previous `topic_domain` label
into the classification prompt as a structured fact, not prose, e.g.:

```
PREVIOUS TURN'S TOPIC DOMAIN: {last_topic.value if last_topic else 'none'}
If this message does not clearly introduce a new, distinct subject, and is a
reaction, follow-up, or continuation of the previous turn, output the SAME
topic domain as the previous turn rather than reclassifying from scratch.
```

This is a correctness-critical fix, not a nice-to-have — the entire point of
the UNFAVORITE hard wall is defeated if it can be bypassed just by changing
register without changing subject.

---

## 5. Pending redesign — curiosity as two orthogonal axes

Current `curiosity_delta` (see file) is a single scalar with one flat
mechanic (novelty bump on topic change, decay otherwise, -20 on hostile
turns). Confirmed bug: a persona can be furious (arousal well above the
hostile-turn -20 hit) and still land in the "ASK. CLARIFY. BE CURIOUS."
directive bucket, because the number alone doesn't reflect *capacity* to
express curiosity. Design below fixes this by splitting curiosity into two
axes that currently share one variable.

### 5a. Capacity gate (mechanical, small change)

`compile_prompt`'s curiosity directive selection must check
`EmotionEngine.has_emotional_capacity(arousal, patience)` **before**
consulting `self.curiosity`, using the same gate already used for banter and
vulnerability. If capacity is false, curiosity's expression is suppressed
regardless of the accumulated score — the drive may still be real
internally, but it doesn't get to surface. Do not zero out `self.curiosity`
itself when this happens; only change which directive string
`compile_prompt` picks.

### 5b. Zone model (the harder design work)

Grounded in Information Gap Theory: curiosity peaks on *partial* familiarity,
not on total ignorance or total mastery. Three zones, mapped onto labels
already produced by the GK split — no new classifier dimension required:

- **Zone of Apathy** → topic is `GENERAL_KNOWLEDGE_UNFAVORITE`, or any
  non-GK topic outside `expertise_topics`. No foothold to form a real
  question. Curiosity accrual should be low/near-zero here — this inverts
  the *old* commented-out behavior which gave bonus curiosity for
  `in_expertise` topics; that direction was backwards per the theory.

- **Zone of Curiosity** (peak) → topic is `GENERAL_KNOWLEDGE_FAVORITE`.
  Partial familiarity, recognizable pattern, real information gap. This
  zone should produce the strongest genuine follow-up-question behavior.
  This is the zone the old binary in/out-of-expertise model had no way to
  isolate at all.

- **Zone of Boredom** → topic `in expertise_topics`, asked in a deep/
  technical (non-GK) register. Full knowledge, closed gap — curiosity
  should default LOW here (inverted from old behavior), **except** for a
  violated-expectations trigger (see 5c).

`Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL` and `Topic.PERSONAL` are
deliberately routed *around* this zone system — interest in the user's life
is a rapport mechanism, not an information-gap mechanism, and forcing it
into apathy/curiosity/boredom buckets doesn't fit.

### 5c. Violated-expectations exception (Zone of Boredom only)

Real curiosity spikes on a fully-known topic need their own trigger, since
the topic itself isn't novel — something about *this specific claim* must
be. Cheapest deterministic proxy, no new schema needed: unusually high
`intensity` on an expertise-zone topic. (A more precise version would add a
dedicated tone or a `contradicts_known_position: bool` field on
`UserMessageMetaDataResponse`, but start with the intensity proxy — it's
free and should be tested before adding schema surface area.)

### 5d. Repetition/boredom decay reuses existing tracking

`topic_repeat_streak` already exists and already measures exactly the
"Routine and Habit" decay mechanism from the theory. Reconnect it to the
Zone of Curiosity specifically (a `GENERAL_KNOWLEDGE_FAVORITE` topic
repeated several turns in a row should decay toward Boredom) rather than the
old flat expertise bonus it was previously wired to (currently commented
out in `curiosity_delta`).

### 5e. Trait-gated "bridging" behavior for Zone of Apathy

Rather than one flat "no knowledge" directive for every persona in the
Apathy zone, gate the *style* of the non-answer on traits:

- High `baseline_security` + low `empathic_resonance` (e.g. current Trump
  config) → **bridging**: don't just admit ignorance, reflexively try to
  relate the foreign topic back to something in `expertise_topics` ("is
  mitochondria some kind of company? a piece of technology?"). This is
  actually the behavior that already emerged unprompted in real testing
  (the mitochondria screenshot) — this makes it a deliberate, reliable
  directive instead of an accident.
  Not genuine curiosity by the strict theory (there's no real foothold) —
  it's an ego-driven reflex specific to this trait combination, and should
  be understood/labeled as such in code comments.
- Otherwise (low security or high empathy) → plain, honest **"I don't know,
  teach me"** — genuine openness to being taught, no forced bridging.

A bridge attempt that gets a real answer from the user should feed into
`learned_topics` (see 5f) — familiarity in that subject rising over the
conversation could eventually graduate it out of Apathy into genuine
Curiosity-zone territory. This is a stretch goal, not required for the
first pass.

### 5f. `learned_topics` (previously scoped, not yet implemented)

Session-scoped, non-decaying dict: `Topic -> {familiarity: float, notes:
List[str]}`. Populated when intent is `CONVERSATION` (user is stating/
explaining, not asking) on a topic outside `expertise_topics`. Learning
rate should scale with `curiosity` (an engaged persona absorbs new
information faster than a bored one) and `novelty_drive`. Never decays —
same rationale as `rapport`: this is memory of what was actually taught in
this relationship, not a mood that fades. Feeds the topic-comprehension
filter: high enough familiarity on an otherwise-unfavorite topic should
shift the directive from flat denial to "you were taught this by the user
earlier — reference it, filtered through your own voice, without claiming
native expertise."

---

## 6. Known smells worth flagging (not blocking, but real)

- `self.user_info` is currently hardcoded as a literal string inside
  `PersonaSession.__init__` — this couples one specific user's identity to
  every session of this persona, which contradicts the whole point of
  `PersonaSession` being per-`(persona, user)`. Should be a constructor
  param populated per-session, not a hardcoded literal, before this goes
  anywhere near multi-user testing.
- `active_persona` is still a module-level singleton — by design, for
  current single-conversation prototype testing only. Known, accepted,
  flagged repeatedly — not a bug to fix yet, just don't build multi-user
  features on top of this file without addressing it first.
- `compile_prompt` has a side effect (`self.is_blocked = True`) despite
  reading like a pure formatter — don't call it more than once per turn
  (e.g. for logging/retries) without accounting for this.

---

## 7. Test cases to run after implementing Section 5

1. Get arousal above 70 via genuine hostility on a `GENERAL_KNOWLEDGE_FAVORITE`
   topic — confirm curiosity's *directive* is suppressed even if the
   underlying `self.curiosity` score is still high from earlier in the
   conversation.
2. Ask a casual question on a favorite-adjacent subject (Zone of Curiosity)
   — confirm stronger follow-up-question behavior than the same subject
   asked in deep/technical register (Zone of Boredom).
3. Stay on the same `GENERAL_KNOWLEDGE_FAVORITE` topic 3-4 turns straight —
   confirm curiosity visibly decays via `topic_repeat_streak`, unlike before
   when this zone didn't exist as a distinct bucket.
4. Deliver a high-intensity claim on a topic squarely in `expertise_topics`
   (Zone of Boredom) — confirm the violated-expectations proxy produces a
   curiosity spike distinct from ordinary Boredom-zone flatness.
5. Ask about a subject outside `expertise_topics` — confirm the bridging
   behavior (if traits warrant it) produces an analogy-seeking question
   rather than either a flat denial or genuine open curiosity.
6. Re-run the exact mitochondria-style sequence (denied on turn N, vague
   bragging follow-up on turn N+1) — confirm the topic-continuity fix
   (Section 4) prevents the reclassification leak this time.