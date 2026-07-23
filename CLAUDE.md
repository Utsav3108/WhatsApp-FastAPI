# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Ripple" — a FastAPI backend for a WhatsApp-style chat app where users converse with AI personas (historical figures, custom characters) powered by Google Gemini. Personas maintain continuous emotional/relationship state across a conversation rather than being stateless per-message. There's also a "Challenges" mode: scripted roleplay scenarios where the user tries to persuade/achieve a goal against a persona, judged turn-by-turn by Gemini and scored win/lose.

## Running the server

```bash
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Requires a `.env` in the repo root (see keys used in `app/database.py`, `app/cache.py`, `app/gemini.py`, `app/s3_service.py`): `GEMINI_API_KEY`, `GEMINI_MODEL`, `POSTGRES_URL`, `REDIS_URL`, `ALLOWED_ORIGINS`, `AWS_*`. Postgres and Redis must be reachable — `app/cache.py` pings Redis at **import time**, so the app (and most tests) will hard-fail on startup without a running Redis instance.

Full stack (app + Redis + Postgres) via Docker:
```bash
docker-compose up --build
```
API docs at `/docs`. Socket.IO is mounted at `/socket.io`.

## Tests

Tests are `unittest.IsolatedAsyncioTestCase`, not pytest (no pytest in requirements). Run from the repo root so `app.*` imports resolve:

```bash
python3 -m unittest discover -s app/tests -p "test_*.py"
python3 -m unittest app.tests.test_challenges                                # one module
python3 -m unittest app.tests.test_challenges.TestChallengesDashboard.test_daily_challenge  # one test
```

Each test case spins up its own in-memory SQLite (`sqlite+aiosqlite:///:memory:`) via `Base.metadata.create_all`, so they don't touch Postgres — but they still need a live Redis (import-time ping) and some hit the real Gemini API over the network (expect failures offline/without a valid key).

## Architecture

### Layers
- `app/main.py` — FastAPI app, CORS, mounts REST routers (all except `auth` behind `Depends(get_current_user)`) and the Socket.IO ASGI app.
- `app/routers/*` — REST endpoints (auth, category, challenge, conversations, reports). `app/persona/persona_router.py` holds persona/profile endpoints (kept out of `routers/` for historical reasons).
- `app/socketio_server.py` — **the live chat path.** REST message endpoints exist, but real-time send/receive, challenge lifecycle events, and all Gemini-triggered replies flow through Socket.IO events (`join`, `send_message`, `leave_chat`, `join_challenge`, `complete_challenge`). `app/websocket.py` is legacy/unused — don't build on it.
- `app/services/*`, `app/persona/persona_service.py` — business logic between routers/socket handlers and `app/crud.py`.
- `app/crud.py`, `app/crud_challenge_attempt.py`, `app/models.py` — async SQLAlchemy 2.0 ORM (Postgres via `asyncpg`).
- `app/cache.py` — Redis read-through cache for persona/challenge lookups (5 min TTL), explicitly invalidated on writes in the service layer.
- `app/gemini.py` — all Gemini calls: persona chat replies (`ask_gemini`), challenge storyline generation, challenge win/lose evaluation (`evaluate_challenge`, structured JSON output), conversation summarization.

### The "Brain" (persona emotional engine) — `app/brain/`

Design intent is documented in `Engine.md`, with a fuller design spec + pending
work log in `PERSONA_ENGINE_DESIGN.md`. This is the system that gives personas
continuous, felt emotional state across a conversation instead of being
stateless per-message — it's the most actively-iterated part of the codebase
and the one most likely to have design intent that isn't obvious from the code
alone, so read this section before touching anything under `app/brain/` or
`app/persona/persona_session.py`.

**Two-layer model.** Every persona has:
- **Traits** — `threat_sensitivity`, `self_regulation`, `novelty_drive`,
  `baseline_security`, `empathic_resonance`. Fixed at construction, never
  mutated. These are rate constants (how fast arousal rises, how fast
  patience drains, how much an apology forgives), not values that move
  turn-to-turn. Distinct personas are defined entirely by different trait
  vectors feeding the same formulas.
- **State** — `arousal`, `patience`, `mood`, `rapport`, `curiosity`, plus a
  `violation_count` and `is_blocked` flag. Mutable, per-session, updated
  every turn.

**Per-request flow**, `Brain.build()` (`app/brain/brain_builder.py`):
1. Hard gate — if the persona is already blocked, short-circuit with a canned
   refusal and skip the Gemini classification call entirely (verified in
   testing: no classification call is made once `is_blocked=True`).
2. `MessageAnalysis.analyze()` — one Gemini call returns a structured
   `UserMessageMetaDataResponse` (intent, tone, intensity 1–100, topic
   domain, language) per `app/brain/schemas.py`, plus a local fastText
   language check via `classifiers.language_classifiers.predict`.
3. Harmful/sexual topic gating — registers a violation against the
   persona's *state* (via `PersonaSession.register_violation()`) so it's
   actually felt in subsequent turns (patience capped down, arousal floored
   up — see below), not just a stateless canned block. Escalates to a
   permanent `is_blocked=True` after repeated violations
   (`VIOLATION_BLOCK_THRESHOLD`, default 2).
4. Non-English input — refused in-character rather than answered.
5. `BrainComponent`s (`PersonaSession`, plus `ResponseStyle`) each
   `update()` internal state, then `compile_prompt()` a directive fragment;
   fragments are joined into the final Gemini system prompt.

**State math** — every transition lives in `app/brain/emotion_engine.py` as a
pure `@staticmethod` (explicit primitive inputs → delta dict, no reference to
`PersonaSession`). `PersonaSession.update()` classifies each turn into
exactly one branch and applies its delta via `_apply()`:

- `compliment_delta` — `Intent.COMPLIMENT` or `Tone.WARM`/`Tone.EXCITEMENT`.
- `hostility_delta` — genuine attacks (`Intent.INSULT`, `Intent.HARMFUL_INTENT`,
  or `Tone.AGGRESSIVE`), evaluated regardless of capacity.
- `banter_delta` — sarcasm/roasting (`Intent.SARCASM`/`Tone.SARCASTIC`), but
  **only** when the persona currently `has_emotional_capacity()` (below
  arousal-70 / above patience-25 thresholds); otherwise the same message
  falls through to `hostility_delta` instead. Encodes "Trump can roast and
  be roasted, but a heated or worn-down persona reads the same joke as an
  attack."
- `apology_delta` — forgiveness is discounted (`anger_modifier = 0.5`) once
  arousal is already ≥70; genuinely furious personas don't forgive as easily.
- `vulnerable_delta` — also capacity-gated: a dysregulated persona can't
  attune to someone else's vulnerability (gets a small patience cost
  instead of the full empathic engagement), matching real emotional-bandwidth
  limits rather than making empathy purely trait-driven.
- `competition_delta`, `conversation_drain`, `content_violation_delta` —
  see `emotion_engine.py` docstrings for the exact weighting rationale on
  each.
- `anger_mood_cap` — applied every turn to the *actual* `mood` value (not
  just the display string): once arousal exceeds 70, mood is clamped to
  ≤0. This is negative-affect dominance — a persona cannot be both genuinely
  furious and reading as "happy" in the same turn, regardless of what else
  happened that turn.

**Topic comprehension / knowledge gating.** `expertise_topics` (a
`List[Topic]` on `PersonaSession`) is the single source of truth for what a
persona is professionally knowledgeable in — it's used both to gate
`compile_prompt`'s knowledge directive AND passed into the Gemini
classification prompt so it can disambiguate casual general-knowledge-style
questions into:
- `GENERAL_KNOWLEDGE_UNFAVORITE` — casual-phrased question on a subject
  outside `expertise_topics` (e.g. "explain mitochondria" to a real-estate
  persona). Hard wall: directive explicitly forbids leaking even partial
  real content.
- `GENERAL_KNOWLEDGE_FAVORITE` — casual-phrased question touching a subject
  *inside* `expertise_topics`. Softer directive: enthusiastic but shallow.
- `GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL` — about the persona's own life,
  ungated by expertise.
- Topic directly `in expertise_topics` (asked in deep/technical register) →
  full expert directive.

⚠️ **Known open bug**: a subject correctly denied via
`GENERAL_KNOWLEDGE_UNFAVORITE` on one turn can get silently reclassified and
leak real content one turn later if the follow-up message is topic-vague
(no explicit subject noun — e.g. a bragging non-sequitur). Root cause: the
classifier has no hard structured anchor to the previous turn's actual
`topic_domain`, only a soft freeform summary string (confirm whether
`PersonaSession.summary` is even being populated anywhere before debugging
further — no write site was found as of this writing). Fix is scoped in
`PERSONA_ENGINE_DESIGN.md` §4: pass the previous turn's topic domain into
the classification prompt as a structured field, with an explicit
instruction to preserve it unless the message clearly introduces a new
subject.

**Curiosity engine — partially implemented, redesign in progress.** Current
`curiosity_delta` is a single scalar (novelty bump on topic change, decay
otherwise, flat -20 on hostile turns). Confirmed issue: a persona can be
genuinely furious and still land in the "ask a follow-up question" directive
bucket, because the -20 hostile-turn hit doesn't reliably drop a
high-accumulated score below the directive threshold. `PERSONA_ENGINE_DESIGN.md`
§5 specifies the fix in progress: splitting curiosity into (a) a capacity
gate reusing `has_emotional_capacity()` — same pattern as banter/vulnerable —
that governs whether accumulated curiosity is allowed to *surface* in
`compile_prompt` at all, and (b) a three-zone model (Apathy /
Curiosity-peak / Boredom) mapped onto the GK topic labels above, replacing
the old flat novelty-only mechanic. Check that doc before modifying
`curiosity_delta` or the curiosity branch of `compile_prompt`.

**Known singleton limitation.** `active_persona` at the bottom of
`persona_session.py` is a single module-level instance (currently hardcoded
to "Donald Trump") — state is process-global, not per-user or per-session.
This is a **deliberate current choice**, made to concentrate effort on
getting the emotional realism right before adding multi-tenancy — not an
oversight to silently fix. Any change to make this multi-tenant needs to key
sessions by `(persona_id, user_id)` instead, per the design notes in
`PERSONA_ENGINE_DESIGN.md` §6, and should be a deliberate, separate piece of
work, not a side effect of an unrelated change.

**Known smell**: `PersonaSession.user_info` is currently a hardcoded literal
string baked into `__init__`, coupling one specific user's identity to every
session of this persona. This directly conflicts with the eventual
per-`(persona, user)` session model above and should become a constructor
param before any multi-user work begins.

### `classifiers/` — not part of the shipped app
Gitignored entirely, and **not copied into the Docker image** (`Dockerfile` only `COPY app/ ./app/`). It's a local ML workspace (fastText training scripts/datasets, a vendored `fastText` git submodule, `.bin` models) that `app/brain/message_analysis.py` imports directly at runtime (`from classifiers.language_classifiers import predict`). This only works when running from a checkout that still has this untracked directory populated with its trained `.bin` models — treat as a known gap if working on deployment/packaging. `classifiers/pipeline.md` and `Engine.md` document the intended fuller classifier pipeline (intent/toxicity/topic/emotion) — most of it is still design notes, not wired into `app/brain/`.

### Personas & traits
`Persona` (in `app/models.py`) is used for both AI characters and human users (`is_human` flag). Real account creation happens in `POST /auth/google` (`app/routers/auth.py`), which creates the `Persona` row on first login; the `get_current_user` dependency used to protect other routes only *looks up* the persona by name and 401s (`"User not found"`) if it doesn't exist yet — it only auto-creates for the dev bypass token (`example_jwt_token`). `Persona.traits` is a `SafeJSON` column that's either a legacy free-text string or a structured `schemas.StructuredTraits` object; `gemini.format_persona_prompt()` handles both, rendering the structured form into prompt sections (identity, personality sliders, values, speech style, humor, backstory, etc.) plus example dialogues.

Note: `Persona.traits` (this DB-level structured trait system) and the five
numeric traits on `PersonaSession` (`threat_sensitivity` etc., from
`app/brain/`) are two separate systems that currently don't talk to each
other — the former drives static prompt formatting via `gemini.py`, the
latter drives the dynamic per-turn emotional state machine in `app/brain/`.
Worth keeping distinct in your head when working across both.

### Challenges
Roleplay scenarios (`Challenge`/`ChallengeContext`/`ChallengeSession`/`ChallengeAttempt` models) with a difficulty-scaled system prompt (beginner/intermediate/advance) and a separate Gemini call after each turn (`evaluate_challenge`) that judges win/loss/timeout against the challenge's stated goal/stakes. Sessions are resumable and track elapsed time server-side for timeout handling; `app/services/challenge_session.py` and `app/services/challenge_service.py` contain the session lifecycle and dashboard (daily/trending/recommended) logic.

### Message send flow (Socket.IO)
`send_message` → persists the user message → spawns a background `asyncio.Task` (`handle_gemini_response`), cancelling any prior in-flight task for the same `chat_key` so overlapping sends to the same chat can't race → DB sessions are opened only for brief read/write windows, with both Gemini calls made outside any open session → AI reply persisted and emitted via `receive_message` to the relevant room (`user:{id}` or `challenge:{session_id}`) → if in a challenge, `evaluate_challenge` runs and a terminal result triggers `complete_challenge`.
