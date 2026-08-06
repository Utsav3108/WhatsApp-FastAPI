# Rippl Backend — Admin API Tasks
**Scope:** Persona Session admin APIs + Persona admin APIs
**Repo:** `project/rippl` (backend)

---

## ✅ Prerequisites — done (as of yesterday)
Alembic setup/migrations, `persona_sessions` table, `messages.persona_session_id` FK, `StructuredTraits` schema update, data backfill for existing personas, and the `chat_key` fork-collision fix are all implemented. Everything below builds directly on top of that.

---

## A. PersonaSession Admin APIs

- [ ] **`GET /admin/persona-sessions`** — grouped-by-pair list
  - One row per `(ai_persona_id, human_persona_id)` pair: persona name, user identity, `fork_count`, aggregated status (e.g. "blocked" if *any* fork is blocked — worth confirming this rollup rule), most recent `updated_at` across forks
  - Filters: has-blocked-fork, persona, user; sort by most recent `updated_at`
- [ ] **`GET /admin/persona-sessions/pairs/{ai_persona_id}/{human_persona_id}/forks`** — expand action: returns every session row for that pair
  - Fields per fork: `id`, `is_blocked`, `block_reason`, `turn_count`, `created_at`, `updated_at`
- [ ] **`GET /admin/persona-sessions/{id}`** — detail view for a single fork: full state row (`arousal`/`patience`/`mood`/`rapport`/`curiosity`/`last_subject`/`topic_repeat_streak`/`violation_count`) + linked message count via `messages.persona_session_id`
- [ ] **`POST /admin/persona-sessions/{id}/reset-block`** — clears `is_blocked`, `block_reason`, and `violation_count` (full reset, confirmed)
  - Log the action (admin id, timestamp) for an audit trail
- [ ] Tests: reset-block on an already-unblocked session, fork disambiguation in listing/detail

## B. Persona Admin APIs

Persona data lives entirely in the existing `traits` (StructuredTraits) and `settings` columns — no new persona-side tables or columns.

- [ ] **`GET /admin/personas`** — list (name, avatar, active flag)
- [ ] **`GET /admin/personas/{id}`** — full object including `traits.brain`, expertise domains (`interests_expertise.expertise`), `identity`/`likes_dislikes`
- [ ] **`POST /admin/personas`** — create; validate the 5 brain trait floats are within expected bounds
- [ ] **`PUT /admin/personas/{id}`** — edit
- [ ] **`DELETE /admin/personas/{id}`** — soft-delete recommended (`persona_sessions` reference personas; no cascade behavior has been specified)
- [ ] Confirm no lingering API/schema references to `relationship_style`, `emotional_profile`, `personality_sliders.{patience,curiosity,warmth}` remain from before the backfill

## C. Cross-cutting

- [ ] Admin-only auth middleware on `/admin/*`
- [ ] Update /docs/API_DOC.md for the frontend team
- [ ] Explicitly out of scope: `challenge_sessions` integration — leave a TODO, don't build combined logic now

---

## Suggested order
1. PersonaSession list + detail (read-only, fastest path to visibility)
2. Reset-block
3. Persona CRUD
4. Auth + docs pass, hand off to frontend