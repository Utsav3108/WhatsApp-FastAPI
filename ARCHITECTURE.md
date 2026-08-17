# Ripple Backend — Architecture

This is the **single source of truth for understanding Ripple**: what it is, the
concepts behind it, and — most importantly — *why* the system is built the way it
is, including the things that were deliberately **not** done and the reasons for
that.

It is written to be read by anyone: a new engineer, a curious outsider, a
reviewer. It does not assume you have read the code. But the code is the ground
truth — this document is distilled *from* the live source, and where the two
ever disagree, the source wins. Supporting design notes live in
[`Engine.md`](Engine.md), [`PERSONA_EMOTION_ENGINE.md`](PERSONA_EMOTION_ENGINE.md),
[`CLAUDE.md`](CLAUDE.md), and [`app/docs/`](app/docs); this document is the
front door to all of them.

## Contents

1. [What Ripple is, and the core bet](#1-what-ripple-is-and-the-core-bet)
2. [High-level system](#2-high-level-system)
3. [Layered architecture & the strict data-access boundary](#3-layered-architecture--the-strict-data-access-boundary)
4. [Request lifecycle: a real-time message](#4-request-lifecycle-a-real-time-message)
5. [Multi-tenant persona sessions (and forks)](#5-multi-tenant-persona-sessions-and-forks)
6. [The persona "Brain": emotional state that persists and decays](#6-the-persona-brain-emotional-state-that-persists-and-decays)
7. [Message understanding: classification, topics, knowledge cutoffs](#7-message-understanding-classification-topics-knowledge-cutoffs)
8. [Two persona systems: static identity vs. dynamic state](#8-two-persona-systems-static-identity-vs-dynamic-state)
9. [Authentication & authorization](#9-authentication--authorization)
10. [Challenges](#10-challenges)
11. [Data model](#11-data-model)
12. [Caching](#12-caching)
13. [External integrations](#13-external-integrations)
14. [The classifiers workspace](#14-the-classifiers-workspace)
15. [Admin API](#15-admin-api)
16. [Deployment & migrations](#16-deployment--migrations)
17. [Further reading](#17-further-reading)

---

## 1. What Ripple is, and the core bet

**Ripple is an AI Persona Communication system.** Users hold ongoing
conversations with AI personas — historical figures, fictional characters, or
custom creations — each powered by Google Gemini. It offers two modes:

- **Persona chat** — open-ended conversation with a persona.
- **Challenges** — scripted roleplay where the user pursues a goal (persuade,
  negotiate, outmaneuver) against a persona, judged turn-by-turn.

**The core bet is statefulness.** Almost every persona chatbot is *stateless*:
each message is answered in isolation, and the character has no memory of how the
conversation has actually felt. Ripple rejects that. Every `(persona, user)`
conversation carries a continuous **emotional and relationship state** — mood,
arousal, patience, rapport, curiosity — that:

- **is updated every turn** by the nature of what the user said (a compliment, an
  insult, a vulnerable admission, playful sarcasm, a competitive dig),
- **is persisted** to the database, so it survives across sessions,
- **decays over real elapsed wall-clock time** between messages (a persona you
  angered cools off if you leave for an hour), and
- **can escalate to blocking** a persona entirely after repeated abuse.

The *why*: a persona that has been insulted for five turns should be genuinely
harder to win back than one greeted warmly — and it should still be a little
guarded an hour later, but not a week later. Modeling that explicitly is the
whole point of the system, and it drives most of the non-obvious architecture
below.

## 2. High-level system

```
  Client (Flutter)
     │  HTTPS (Bearer ID token)      ┌──────────────────────────────────────┐
     ├───────────────────────────────▶  REST routers ───┐                   │
     │                               │                   ▼                   │
     │  Socket.IO (WebSocket)        │  Socket.IO ────▶  Service layer ──────┼──▶ Redis
     └───────────────────────────────▶  handlers  ──┐    │       │           │   (cache +
                     ▲               │              │    ▼       ▼           │    SIO manager)
                     │               │              │  CRUD    Gemini / S3   │        ▲
                     │               │              ▼  layer                 │        │
                     │               │           Brain engine ──▶ Gemini     │        │
                     │               └──────────────┼────────────────────────┘        │
                     │                              ▼                                  │
                     │                          PostgreSQL                            │
                     └──── cross-worker fan-out (multi-process emits) ────────────────┘
```

`app/main.py` builds one FastAPI app: it registers the REST routers (each behind
an auth dependency) and mounts the Socket.IO ASGI app at `/socket.io`. Redis
plays **two** roles — a read-through cache *and* the Socket.IO
`AsyncRedisManager`, so emits fan out correctly when the app runs as more than
one worker/process (a deliberate choice to keep the real-time layer horizontally
scalable rather than pinned to a single process).

## 3. Layered architecture & the strict data-access boundary

Every domain (persona, persona-session, challenge, reports, admin, …) follows the
same three layers, and the split is enforced as a **hard rule**, not a
convention.

```
  PRESENTATION   REST routers  ·  Socket.IO handlers
                      │   ▲
     call service ────┘   └──── Pydantic models back
                      ▼
  SERVICE        *_service.py          ──▶ Redis cache   (check first)
                 (cache + Pydantic         ──▶ CRUD layer    (on a miss)
                  conversion live here)
                      │   ▲
       fetch on miss ─┘   └──── raw ORM rows
                      ▼
  DATABASE       *crud* files  ──▶  PostgreSQL
                 (the ONLY place a query ever runs)
```

- **Database / CRUD layer** — the module's `*crud*` file is the *only* place a
  query ever runs (`select`, `insert`, `session.add`, `session.execute`, …). It
  returns raw ORM rows. Each domain owns its own CRUD file next to its code:
  `app/crud.py`, `app/crud_challenge_attempt.py`, `app/crud_reports.py`,
  `app/persona/persona_crud.py`, `app/persona/persona_session_crud.py`,
  `app/admin/*_crud.py`.
- **Service layer** — owns the read path: check Redis first; on a miss, call
  CRUD, convert the ORM result into a Pydantic model, populate the cache, return
  the model. It is the *only* layer that knows about both the cache and CRUD.
  See `persona_service.get_persona_by_id` for the canonical read-through shape.
- **Presentation layer** — routers and Socket.IO handlers call a service method
  and get a Pydantic model back. They never touch the cache or CRUD directly.

**Why so strict?** Two reasons the codebase actually depends on. First, the read
path's caching and Pydantic-conversion responsibility has exactly one home (the
service layer) instead of leaking into handlers. Second, database sessions can be
kept *short and explicit* — which matters enormously for the real-time path,
where a long-held session across a multi-second Gemini call would pin a
connection for no reason (see §4). If DB calls could happen anywhere, that
discipline would be impossible to maintain.

## 4. Request lifecycle: a real-time message

The live chat path is Socket.IO (`app/socketio_server.py`), not REST. The design
goal is: never block the socket on Gemini, never let two replies to the same
conversation race, and never hold a DB connection open across a model call.

```
  Client ──send_message──▶ send_message handler
    1. load PersonaSession for (persona, user) pair          [DB, brief]
    2. persist user message  (stamped with persona_session_id) [DB, brief]
    3. spawn handle_gemini_response task, keyed by chat_key
         (cancels any prior in-flight task for THIS fork)
  ───────────── background task — no DB session held across Gemini ──────────
    4. read persona / user rows, then release                [DB, brief]
    5. Brain.build(): 2 concurrent classify calls   ───▶ Gemini
    6. generate persona reply                        ───▶ Gemini
    7. persist reply + save() mutated session state          [DB, brief]
    8. emit receive_message   ───▶ room  user:{id} | challenge:{sid}
          └─ if persona just blocked this turn: emit persona_blocked
    9. (challenge only) evaluate_challenge           ───▶ Gemini
          └─ terminal result: complete_challenge ───▶ challenge_completed
```

The load-bearing details, each there for a concrete reason:

- **Fork-scoped `chat_key` + task cancellation.** A new `send_message` cancels
  the previous in-flight `handle_gemini_response` task *for the same fork*. The
  key is built from the resolved `persona_session_id`
  (`user_{sender}_persona_session_{id}`), not the raw sender/receiver pair —
  otherwise two forks of the same pair would collapse onto one key and cancel
  each other's replies.
- **Short-lived, phased DB sessions.** Reads (phase 1), the reply write + state
  save (phase 3), and the challenge status check happen in separate brief
  windows. Both Gemini calls (`ask_gemini`, `evaluate_challenge`) run with *no*
  session held — the reason the strict layering in §3 exists.
- **Fork-scoped history.** The last ~10 messages fed to Gemini are pulled by
  `persona_session_id`, so history from a *different* fork (e.g. a blocked
  session the user restarted from) never leaks into this fork's context.
- **State is saved conditionally.** `save(state_changed=...)` only advances the
  decay anchor when the turn actually mutated emotional state — a hard-gated or
  language-refused turn pokes the row (bumping recency) without falsely resetting
  the decay clock.

## 5. Multi-tenant persona sessions (and forks)

> This is the single biggest thing to understand, and the single most common
> stale belief: **Ripple is fully multi-tenant.** There is no global singleton
> persona. Every conversation is its own persisted session.

A **persona session** is one running relationship between an **AI persona** and a
**human persona**, identified by the pair `(ai_persona_id, human_persona_id)`.
It lives in the `persona_sessions` table and is represented in memory by
`app/persona/persona_session.py`'s `PersonaSession` class. The class is a
hydrate/dehydrate boundary — it never opens a DB session itself; `load()` and
`save()` are the only two DB-aware methods, called once per message and never
cached across messages.

```
  send_message for (ai, human) pair
    │
    ├─ persona_session_id supplied? ─ yes ─▶ load that exact fork (ownership-checked)
    │                                          │
    │                                          ├─ belongs to this pair? ─ no ─▶ reject (MismatchError)
    │                                          └─ yes ─▶ hydrate ─┐
    │                                                             │
    └─ no ─▶ load latest fork (updated_at desc, id desc)          │
               │                                                  │
               ├─ any prior fork? ─ no ─▶ baseline defaults ──────┤ (first-ever contact)
               └─ yes ─▶ hydrate ─────────────────────────────────┤
                                                                   ▼
                                              within blocked_until ?
                                                 ├─ yes ─▶ freeze as stored, skip decay
                                                 └─ no  ─▶ lazy auto-unblock + apply time-decay
```

**Forks.** A pair can have *multiple* concurrent sessions — deliberately: there
is **no** unique constraint on `(ai_persona_id, human_persona_id)`. If a user
angers a persona into a block and wants a clean slate, the client calls
`PersonaSession.create_new()` (exposed via `POST /persona-sessions/new`), which
starts a fresh baseline fork and — because it saves immediately with a new
`updated_at` — becomes the "latest" fork that future no-id loads pick up. The old
fork isn't destroyed; it sits alongside as history (surfaced via
`GET /personas/{id}/chats`).

**Ownership is enforced, never fudged.** When a client pins a specific
`persona_session_id`, it *must* belong to that pair or the message is rejected
(`PersonaSessionMismatchError`). The code never silently falls back to "latest"
on a mismatch — that would defeat the point of pinning a fork and could route a
reply into the wrong conversation. The same reject-don't-fall-back rule governs
task cancellation in `leave_chat` and the `check_unblock_status` poll.

**Why sessions are *not* in the Redis cache.** Unlike personas and challenges,
`persona_sessions` is deliberately excluded from the read-through cache: it
mutates every single turn, so a naive TTL cache would invite lost-update races on
concurrent or cancelled turns. State correctness beats a cache hit here.

## 6. The persona "Brain": emotional state that persists and decays

`app/brain/` and `PersonaSession` together are the emotion engine. This is a
readable overview; the exhaustive spec is in [`Engine.md`](Engine.md) and
[`PERSONA_EMOTION_ENGINE.md`](PERSONA_EMOTION_ENGINE.md).

**Two layers: traits vs. state.**

- **Traits** — `threat_sensitivity`, `self_regulation`, `novelty_drive`,
  `baseline_security`, `empathic_resonance`. Fixed at construction, never
  mutated. They are *rate constants*: how fast arousal rises, how fast patience
  drains, how much an apology forgives, how quickly the persona cools off
  between conversations. Two personas differ *entirely* by their trait vector
  feeding the same formulas.
- **State** — `arousal`, `patience`, `mood`, `rapport`, `curiosity`, plus
  `violation_count` and block flags. Mutable, per-session, updated every turn and
  persisted.

**Per-turn flow — `Brain.build()`** (`app/brain/brain_builder.py`):

```
  incoming message
    │
    ├─ session already blocked?  ─ yes ─▶ canned refusal (skip Gemini entirely)
    └─ no
        ├─ analyze()  ──▶ 2 concurrent Gemini classify calls (metadata + topic)
        ├─ harmful / sexual topic?  ─ yes ─▶ register_violation()
        │                                     (felt in later turns; block after threshold)
        ├─ language not understood? ─ yes ─▶ refuse in-character
        └─ else ─▶ each BrainComponent update()s state, then compile_prompt()s a directive
                     └─▶ fragments joined into the Gemini system prompt
```

**The state math** (`app/brain/emotion_engine.py`) is a set of pure static
functions — primitive inputs in, delta dict out, zero side effects. `update()`
routes each turn into exactly one branch. The interesting, deliberate rules:

- **Capacity gating.** Sarcasm reads as playful *banter* only while the persona
  `has_emotional_capacity()` (arousal < 70 and patience > 25). A heated or
  worn-down persona reads the *same* joke as an attack and routes to
  `hostility_delta` instead. Vulnerability attunement is gated the same way — a
  dysregulated persona can't attune to someone else's difficulty; it lands as one
  more demand. The *why*: emotional bandwidth is finite, and the same input
  should mean different things depending on the persona's current state.
- **Competition ≠ attack.** A competitive dig costs *patience* (it's effortful to
  parry), not *arousal* (which models threat detection). Trash talk is delivered
  with heat by definition, so competition is checked *before* tone-based
  hostility — otherwise it would be dead code.
- **Discounted forgiveness.** An apology forgives less once arousal ≥ 70:
  genuinely furious personas don't let go as easily.
- **Negative-affect dominance.** Once arousal > 70, mood is clamped ≤ 0 on the
  *real* state every turn — a persona can't be both furious and "happy" in the
  same turn, and mood can't silently stay inflated underneath an angry directive.

**Time decay between messages** (`time_cooldown_delta`, `half_life_hours`).
Applied at `load()` based on elapsed wall-clock time since the last real state
change: arousal relaxes toward 0, mood drifts to neutral, patience regenerates
(faster for a secure persona). The per-persona half-life reuses the *same* two
traits — a secure, even-tempered persona cools down within the hour; a
grudge-holder is still simmering the next day with no new provocation. **Rapport
is deliberately excluded from decay**: it's durable relationship memory, not a
mood, so trust you've built doesn't evaporate overnight.

**Blocking is stateful and self-expiring.** Repeated harmful/sexual violations
(or arousal hitting the ceiling) set `is_blocked` with a `blocked_until`
timestamp. Blocks auto-expire lazily on the next `load()` — no background job
needed. The client can poll `check_unblock_status` (which acks the result and
emits `persona_unblocked`), and a turn that trips a fresh block emits
`persona_blocked`.

**Curiosity is a redesigned, zone-based engine.** Rather than a flat novelty
scalar, curiosity maps the classifier's topic label onto **Information Gap
Theory** zones (`CuriosityZone`): *Apathy* (a subject outside expertise),
*Curiosity* (partial familiarity — the peak), *Boredom* (deep mastery, closed
gap), *Routed-around* (personal/rapport topics, outside the gap model), and
*Anachronistic* (something beyond a historical persona's lifetime — the largest
possible gap). Whether accumulated curiosity is even *allowed to surface* in the
prompt is capacity-gated too: an angry persona doesn't get to be inquisitive.

## 7. Message understanding: classification, topics, knowledge cutoffs

Before the Brain can react, it must understand the message. `MessageAnalysis`
(`app/brain/message_analysis.py`) runs **two independent Gemini classification
calls concurrently** (`asyncio.gather`), and only proceeds once both return:

1. **Affective metadata** — `intent`, `tone`, `intensity` (1–100), and whether
   the message is in a language the persona understands.
2. **Topic detection** — the topic domain, a free-text `subject_label`, an
   `is_same_subject` continuity flag, and `requires_post_cutoff_knowledge`.

**Why two calls?** Affective classification and topic disambiguation need
different context and different reasoning; splitting them lets each be tuned,
retried, or swapped independently, and they run in parallel so there's no latency
cost.

Two subtle, deliberate mechanics:

- **The topic-continuity fix.** A subject the persona correctly refused on turn N
  used to leak on a topic-vague follow-up at turn N+1 (a brag with no explicit
  subject noun would get reclassified). The fix is `is_same_subject`: the model
  judges continuity *directly* against the previous messages, and the engine
  trusts that judgment instead of comparing drifting free-text labels. The
  `subject_label` is kept **for logging only** and is explicitly never used for
  novelty detection.
- **Knowledge cutoffs for historical personas.** A persona can carry a
  `knowledge_cutoff_date` (e.g. Churchill's). The topic classifier then flags
  anything requiring post-cutoff knowledge — even within the persona's expertise
  (asking a historical statesman about a living politician) — and the prompt
  makes the persona genuinely curious about the future rather than hallucinating
  an answer.

**Knowledge gating.** A persona's free-text `expertise` list drives how questions
are answered: an in-domain technical question gets a full **expert** answer; a
casual question inside expertise gets enthusiastic-but-shallow; a subject *outside*
expertise is a hard wall (with an optional trait-driven "relate it to something I
do know" bridging behavior for a secure, low-empathy persona); questions about the
persona's own life route around gating entirely.

## 8. Two persona systems: static identity vs. dynamic state

`Persona.traits` is a `StructuredTraits` object (`app/schemas.py`) — or a legacy
free-text string, which the code still tolerates. It carries two *distinct*
things that feed two *distinct* systems, and understanding the split matters:

- **Static identity** — `identity`, `personality_sliders`, `values`,
  `speech_style`, `humor`, `backstory`, and `example_dialogues`. These are
  rendered once into a fixed prompt preamble by `format_persona_prompt()`
  (`app/gemini.py` / `persona_prompt_formatting.py`).
- **Dynamic rate constants** — `traits.brain` (`BrainProfileModel`) holds the
  five Brain trait values. At session `_baseline()` time these are pulled out to
  seed the emotion engine.

**Why they connect now (and used to be a smell).** Earlier, static "patience/
warmth" personality sliders coexisted with the Brain's live per-turn patience,
creating genuine ambiguity about which number a prompt meant. Those duplicated
sliders were removed; the Brain owns those dynamics, and `traits.brain` is the
single explicit place a persona's emotional rate constants live. `traits.brain`
is an explicit typed field (not a loose JSON key) precisely because Pydantic v2
would otherwise silently strip an unrecognized key on the next round-trip — it
would *look* saved and then vanish.

Every turn's final Gemini prompt is therefore: the static identity preamble +
the Brain's live behavioral directives (from §6) + a response-style component.

## 9. Authentication & authorization

- **Login** — `POST /auth/google` (`app/routers/auth.py`) verifies a Google ID
  token against Google's tokeninfo endpoint, then finds-or-creates the caller's
  `Persona` row (`is_human=True`) and refreshes their contact info.
- **Protecting routes** — every router except `auth` is mounted behind
  `Depends(get_current_user)`. That dependency only **looks up** the persona by
  the verified identity and returns `401 "User not found"` if the row doesn't
  exist yet; it auto-creates *only* for the dev-bypass token
  (`example_jwt_token`). This keeps account creation to the single explicit login
  path in normal operation.
- **Admin** — `/admin/*` stacks `Depends(get_current_admin_user)`
  (`app/admin/admin_auth.py`) on top, requiring the persona's `is_admin` flag.
  Admin mutations are attributed in `admin_audit_logs`.

## 10. Challenges

Challenges are roleplay scenarios modeled by `Challenge`, `ChallengeContext`,
`ChallengeSession`, and `ChallengeAttempt` (`app/models.py`); lifecycle and
dashboard logic live in `app/services/challenge_service.py` and
`app/services/challenge_session.py`.

- **Difficulty-scaled prompts** — beginner (cooperative), intermediate
  (realistic), advance (skeptical/stubborn) change how hard the persona is to
  persuade, injected directly into the system prompt.
- **Turn-by-turn judging** — after each turn, a *separate* Gemini call
  (`evaluate_challenge`) returns structured JSON judging win / loss / timeout
  against the challenge's stated goal and stakes.
- **Resumable + server-timed** — sessions track `elapsed_seconds` /
  `last_resumed_at` so timeouts are enforced server-side and survive pause/resume.

**A deliberate boundary:** Challenges do **not** use the Brain/`PersonaSession`
engine. They build their own self-contained system prompt in `ask_gemini`,
independent of emotional state. This is why a message row carries *either* a
`challenge_session_id` *or* a `persona_session_id` — and why there is
intentionally no DB constraint forcing them mutually exclusive, since a future
task may wire the Brain into challenges too.

## 11. Data model

All tables are defined in `app/models.py` (async SQLAlchemy 2.0). A rendered
diagram is checked in as [`er-diagram.png`](er-diagram.png).

```
  personas  (id, name, traits[SafeJSON], is_human, is_admin, is_active)
      │  dual-purpose: BOTH human accounts AND AI characters
      ├──< messages            .sender_id / .receiver_id
      ├──< persona_sessions    .ai_persona_id + .human_persona_id
      ├──< challenge_sessions  .user_id + .persona_id
      ├──< challenge_attempts  .user_id + .persona_id
      ├──< ai_content_reports  .persona_id
      └──< admin_audit_logs    .admin_id

  persona_sessions  (id, ai_persona_id, human_persona_id,
                     arousal, patience, mood, rapport, curiosity,
                     violation_count, is_blocked, blocked_until,
                     last_emotional_update_at, updated_at)
      └──< messages            .persona_session_id   ← fork-scoped chat history

  challenges  (id, title, difficulty)
      ├──1 challenge_contexts  .challenge_id  (goal, stakes, storyline)
      └──< challenge_sessions  .challenge_id  (status, elapsed_seconds)
               ├──< challenge_attempts  .challenge_session_id  (won, attempt_number)
               └──< messages            .challenge_session_id

  messages  (id, sender_id, receiver_id, text, is_user,
             challenge_session_id?, persona_session_id?)   ← one OR the other
      └──< ai_content_reports  .message_id

  categories  (id, name)

  Legend:   ──<  one-to-many      ──1  one-to-one      ?  nullable / either-or
```

Modeling decisions worth calling out:

- **`Persona` is dual-purpose** — it represents *both* human accounts
  (`is_human=True`, created on login) and AI characters. That's why the two sides
  of `persona_sessions`, and `messages.sender_id` / `receiver_id`, all point at
  the same table.
- **`persona_sessions` has no uniqueness on the pair** — forks are a feature
  (§5). "Latest" is resolved by `updated_at desc, id desc`; the `id` tiebreaker
  matters because SQLite's clock has only second resolution and even Postgres can
  tie under fast successive writes.
- **`last_emotional_update_at` vs. `updated_at`** are separate on purpose:
  the former is the *decay anchor* (moved only when state truly changed), the
  latter is *fork-recency* (bumped on every save). Conflating them would corrupt
  either decay math or fork selection.
- **`SafeJSON` / `CompatibleJSON`** map to Postgres `JSONB` but degrade to
  `TEXT` / `JSON` on SQLite, so the same models back both production and the
  in-memory test suite. `SafeJSON` also accepts either a structured Pydantic
  object or a legacy free-text string (used by `Persona.traits`).
- **`admin_audit_logs.target_id`** is a plain string discriminated by
  `target_type`, so one column can reference either a persona or a
  persona-session without two nullable FKs.

## 12. Caching

`app/cache.py` is a Redis read-through cache for persona/challenge lookups with a
5-minute TTL. The service layer checks Redis first and, on a miss, fetches via
CRUD and populates the cache; writes explicitly invalidate the relevant keys.
`persona_sessions` is intentionally *excluded* (§5).

> ⚠️ `app/cache.py` **pings Redis at import time**, so the app (and most tests)
> hard-fail on startup without a running Redis instance. Redis is also the
> Socket.IO cross-worker manager (§2), so it is not optional infrastructure.

## 13. External integrations

- **Google Gemini** (`app/gemini.py`) — the single home for all Gemini calls:
  persona chat replies (`ask_gemini`, which delegates the non-challenge system
  prompt to `Brain.build()`), the two message-classification calls
  (`app/brain/message_analysis.py`), challenge storyline generation, challenge
  evaluation (`evaluate_challenge`, structured JSON), and summarization. Safety
  filters are set to `BLOCK_NONE` because the *persona*, not Gemini's default
  guardrails, is the intended arbiter of in-character behavior — harmful content
  is instead handled explicitly by the Brain's violation/blocking system.
- **AWS S3** (`app/s3_service.py`) — image-message upload and URL generation;
  messages reference the object via `messages.image_object_name`.

## 14. The classifiers workspace

`classifiers/` at the repo root is a **local ML workspace** — fastText training
scripts, datasets, a vendored `fastText` submodule, and trained `.bin` models. It
is **gitignored** and **not** copied into the Docker image (the `Dockerfile` only
`COPY app/ ./app/`). `app/brain/message_analysis.py` retains an import hook for
it, though the fastText language path is currently commented out in favor of the
Gemini-based language check. Treat the fastText models as a **known
deployment/packaging gap**: anything that re-enables that import only works from a
checkout that still has the trained models present.
`classifiers/pipeline.md` and [`Engine.md`](Engine.md) describe the fuller
intended classifier pipeline, most of which remains design notes.

## 15. Admin API

`app/admin/` exposes an internal `/admin/*` REST API gated by `is_admin` on top of
normal Google-login auth. Current scope: **persona-session** inspection and
reset-block, and **persona** roster CRUD with soft-delete via `Persona.is_active`.
Every admin action is attributed in `admin_audit_logs`
(`app/admin/admin_audit_crud.py`). Challenge-session admin visibility is
explicitly out of scope for now.

## 16. Deployment & migrations

- **Docker** — `docker-compose.yml` runs three services: the FastAPI app
  (port 8000), Redis (`redis/redis-stack`), and Postgres 17, each with a
  persistent volume. The `Dockerfile` builds from `python:3.11-slim` and copies
  only `app/`.
- **Migrations** — Alembic (`alembic/`, `alembic.ini`). The app also calls
  `Base.metadata.create_all` on startup for convenience.
- **Config** — all secrets/config come from `.env` (`python-dotenv`); see the
  [README](README.md#getting-started-local) for the full key list.
- **Known gap** — `classifiers/` is not packaged into the image (§14).

## 17. Further reading

- [`Engine.md`](Engine.md), [`PERSONA_EMOTION_ENGINE.md`](PERSONA_EMOTION_ENGINE.md)
  — the emotion engine's full design spec and open work log.
- [`app/docs/API_DOC.md`](app/docs/API_DOC.md) — REST API reference.
- [`app/docs/socketio_server_events.md`](app/docs/socketio_server_events.md) —
  Socket.IO event reference.
- [`CLAUDE.md`](CLAUDE.md) — engineering guidance for working in the codebase.
- `app/claude_docs/` — task & design notes (admin API, topic system, time decay,
  persona persistence, …).
- [`er-diagram.png`](er-diagram.png) — rendered ER diagram.
