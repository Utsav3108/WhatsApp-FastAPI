# Ripple — Backend

**Ripple is an AI Persona Communication system** — a FastAPI backend where users
hold real, ongoing conversations with AI personas (historical figures, fictional
characters, or custom creations) powered by **Google Gemini**. What sets it
apart: personas aren't stateless chatbots. Each `(persona, user)` conversation
runs a continuous **emotional/relationship engine** (the "Brain") that carries
mood, arousal, patience, rapport, and curiosity across the whole exchange —
persisted, decaying over real time between messages, and forkable — so how a
persona reacts depends on the entire history of how the relationship has gone.

Ripple also ships a **Challenges** mode: scripted roleplay scenarios where the
user tries to persuade or outmaneuver a persona toward a goal, judged
turn-by-turn by Gemini and scored win/lose.

> Backend-only repo. The Flutter mobile client lives elsewhere.

---

## Features

- **Real-time chat over Socket.IO** — live send/receive and challenge lifecycle
  events (the primary chat path; REST endpoints exist but the live path is
  Socket.IO).
- **Gemini-powered persona replies** — persona chat, challenge storyline
  generation, turn-by-turn challenge judging, and conversation summarization.
- **Stateful persona "Brain"** — a per-`(persona, user)` emotion engine
  (fixed traits → mutable state) that makes personas react in-character over the
  whole relationship. State is persisted, decays over real elapsed time between
  messages, supports multiple concurrent "forks" per pair, and can auto-block a
  persona after repeated violations.
- **Challenges mode** — difficulty-scaled roleplay scenarios with resumable
  sessions, server-side timeouts, and Gemini win/lose evaluation.
- **Google OAuth** — sign-in via `POST /auth/google`; personas double as human
  user accounts.
- **Admin API** — internal `/admin/*` surface for persona-session inspection and
  persona roster management, gated by an admin flag and backed by an audit log.
- **S3 image uploads** — image messages stored in S3.
- **Redis read-through caching** — 5-minute TTL on persona/challenge lookups,
  explicitly invalidated on writes.
- **Async Postgres** — SQLAlchemy 2.0 async ORM over `asyncpg`, with Alembic
  migrations.

## Tech stack

| Concern | Choice |
|---|---|
| Web framework | FastAPI + Starlette (`uvicorn`) |
| Real-time | Socket.IO (`python-socketio`), mounted at `/socket.io` |
| Database | PostgreSQL via SQLAlchemy 2.0 **async** + `asyncpg` |
| Migrations | Alembic |
| Cache | Redis (`redis-py`) |
| Validation | Pydantic v2 |
| AI | Google Gemini (`google-genai`) |
| Object storage | AWS S3 (`boto3`) |
| Auth | Google OAuth ID-token verification (`google-auth`) |

See `requirements.txt` for exact versions.

---

## Project structure

Everything ships under `app/`. The codebase follows a strict
**presentation → service → CRUD** layering with a hard rule that *all* database
access lives only in `*crud*` files (see [ARCHITECTURE.md](ARCHITECTURE.md)).

| Path | What it holds |
|---|---|
| `app/main.py` | FastAPI app entrypoint: CORS, router registration, auth dependencies, and the Socket.IO ASGI mount. |
| `app/socketio_server.py` | **The live chat path.** Socket.IO event handlers: `join`, `send_message`, `leave_chat`, `join_challenge`, `complete_challenge`, and Gemini-triggered replies. |
| `app/websocket.py` | Legacy raw-WebSocket helpers — **unused**, don't build on it. |
| `app/routers/` | REST routers: `auth`, `challenge`, `category`, `conversations`, `reports`. |
| `app/persona/` | Persona & profile domain: `persona_router.py`, `persona_service.py`, `persona_crud.py`, `persona_session_crud.py`, the DB-hydrated Brain session (`persona_session.py` — `load`/`save`/`create_new` per `(persona, user)` pair), and prompt formatting (`persona_prompt_formatting.py`). |
| `app/services/` | Business logic between handlers and CRUD: `challenge_service.py`, `challenge_session.py`, `message_service.py`. |
| `app/brain/` | The persona **emotion engine** — traits/state model, `emotion_engine.py` (pure state math), `brain_builder.py` (per-turn prompt assembly), `message_analysis.py` (Gemini classification), `response_style.py`, `schemas.py`. See [ARCHITECTURE.md](ARCHITECTURE.md) & [Engine.md](Engine.md). |
| `app/admin/` | Internal admin-only REST API (`/admin/*`): router, admin auth gate, per-domain CRUD, and the audit-log CRUD. |
| `app/crud.py`, `app/crud_challenge_attempt.py`, `app/crud_reports.py` | Top-level DB access boundary (one CRUD file per domain; persona/admin have their own alongside their code). |
| `app/cache.py` | Redis read-through cache. **Pings Redis at import time** — the app won't start without a reachable Redis. |
| `app/gemini.py` | All Gemini calls (chat replies, storyline generation, challenge evaluation, summarization) and persona prompt formatting. |
| `app/database.py` | Async SQLAlchemy engine/session setup and the declarative `Base`. |
| `app/models.py` | ORM models + the `SafeJSON` / `CompatibleJSON` column types. |
| `app/schemas.py` | Pydantic request/response schemas. |
| `app/s3_service.py` | S3 image upload/URL helpers. |
| `app/enums.py` | Shared enums (e.g. `ChallengeResult`). |
| `app/data.json`, `app/challenge.json` | Seed data for personas / challenges. |
| `app/docs/` | REST + Socket.IO reference docs (`API_DOC.md`, `socketio_server_events.md`). |
| `app/claude_docs/` | Task & design notes. |
| `app/AppServices/` | `connection_manageer.py` — connection-tracking helper. |

Root-level:

| Path | What it holds |
|---|---|
| `alembic/`, `alembic.ini` | Database migrations. |
| `Dockerfile`, `docker-compose.yml` | Container build + full stack (app + Redis + Postgres). |
| `Engine.md`, `PERSONA_EMOTION_ENGINE.md` | Design docs for the persona emotion engine. |
| `er-diagram.png` | Visual entity-relationship diagram of the data model. |
| `classifiers/` | Gitignored local ML workspace (fastText models/scripts). `app/brain/message_analysis.py` keeps an import hook for it (the fastText language path is currently commented out in favor of a Gemini check). **Not** copied into the Docker image — see [ARCHITECTURE.md](ARCHITECTURE.md#14-the-classifiers-workspace). |
| `CLAUDE.md` | In-depth guidance for AI coding assistants (also a useful engineering reference). |

---

## Getting started (local)

Requires **Python 3.11+**, a reachable **PostgreSQL**, and a running **Redis**
(pinged at import time — the app hard-fails on startup without it).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Create a `.env` in the repo root with:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.x-...
POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/ripple
REDIS_URL=redis://localhost:6379
ALLOWED_ORIGINS=http://localhost:3000,https://your.app
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=...
AWS_S3_BUCKET=...
```

- Interactive API docs: <http://localhost:8000/docs>
- Socket.IO endpoint: `ws://localhost:8000/socket.io/`

## Docker

Run the full stack (app + Redis + Postgres) with persistent volumes:

```bash
docker-compose up --build
```

Then open <http://localhost:8000/docs>. Environment variables are injected from
your `.env`. Stop with `docker-compose down`.

> Note: `classifiers/` is not copied into the image, so the fastText models in
> `app/brain/message_analysis.py`'s import hook are a known packaging gap for
> containerized runs. See [ARCHITECTURE.md](ARCHITECTURE.md#14-the-classifiers-workspace).

## Running tests

Tests are `unittest.IsolatedAsyncioTestCase` (not pytest). Each test spins up its
own in-memory SQLite, but they still need a **live Redis** (import-time ping) and
some hit the **real Gemini API** (expect failures offline or without a valid key).
Run from the repo root:

```bash
python3 -m unittest discover -s app/tests -p "test_*.py"
python3 -m unittest app.tests.test_challenges                    # one module
python3 -m unittest app.tests.test_challenges.TestChallengesDashboard.test_daily_challenge  # one test
```

---

## API & real-time overview

- **REST reference:** [`app/docs/API_DOC.md`](app/docs/API_DOC.md)
- **Socket.IO reference:** [`app/docs/socketio_server_events.md`](app/docs/socketio_server_events.md)

All REST routes except `POST /auth/google` (and the `/` root) require a Google
ID token as a Bearer credential. Admin routes additionally require an admin
persona.

Live chat runs over Socket.IO. Key events at a glance:

| Event | Direction | Purpose |
|---|---|---|
| `join` | client → server | Register a user session / join the `user:{id}` room. |
| `send_message` | client → server | Send a chat message; triggers the Gemini reply flow. |
| `leave_chat` | client → server | Leave a chat and cancel its in-flight reply task. |
| `check_unblock_status` | client → server (acked) | Poll whether a persona fork is still blocked. |
| `join_challenge` | client → server | Join a `challenge:{session_id}` room. |
| `complete_challenge` | client → server | Report a client-side terminal result (e.g. timeout). |
| `receive_message` | server → client | Delivers messages, including AI replies. |
| `persona_blocked` / `persona_unblocked` | server → client | Fork blocked this turn / became unblocked. |
| `challenge_completed` | server → client | Terminal challenge result (win/lose/timeout). |

---

## Architecture

Ripple is built as clean presentation → service → CRUD layers, with the Brain
emotion engine and Socket.IO chat path as its most distinctive pieces. For the
full picture — system diagram, request lifecycle, the emotion engine, the data
model, caching, and deployment — read:

### 📐 [ARCHITECTURE.md](ARCHITECTURE.md)

AI-assistant-oriented guidance (also a good deep reference) lives in
[`CLAUDE.md`](CLAUDE.md).

## License

MIT License. See [LICENSE](LICENSE) for details.

---

*Built with FastAPI, Socket.IO, SQLAlchemy (async Postgres), Redis, and Google Gemini.*
