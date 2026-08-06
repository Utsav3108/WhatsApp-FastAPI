# Task: Persona Details Page — Backend APIs

**Scope:** backend only. No frontend work in this task.

Two new read-only REST endpoints, both scoped to the AI persona being viewed
and the currently authenticated user (the human persona from
`get_current_user`):

1. **Persona details** — static profile info for the persona.
2. **Persona chats list** — every chat (session/fork) the current user has
   ever had with that persona, including blocked ones, each tagged with a
   status.

> **Before writing any code:** this doc was written from the existing
> design-conversation rollup (`base_session_chat_context`) and `CLAUDE.md`,
> not from re-reading the live files. Per the process note already logged in
> that rollup (§11): treat field names, table names, and "already exists"
> claims below as *probably* accurate, and confirm against the actual current
> files (`app/models.py`, `app/persona/persona_router.py`,
> `app/persona/persona_service.py`, `app/persona/persona_crud.py`,
> `app/persona/persona_session_crud.py`, `app/persona/schemas.py`) before
> implementing. Specifically confirm:
> - The exact field/column names for persona description and category
>   (category has its own router per `CLAUDE.md`, so it may be a relation,
>   not a plain string column — check `app/routers/category.py` and the
>   `Persona` model).
> - Whether `persona_sessions` currently has a `blocked_until` column
>   (§6 of the rollup — wall-clock auto-expiring block) or whether blocking
>   is still permanent-only as originally documented. The rollup's own status
>   note is ambiguous on whether §6 shipped. This changes how "blocked" is
>   computed below — see API 2.

---

## API 1 — Persona Details

**Purpose:** populate the top of the persona details page. Static info only —
no emotional/session state.

**Suggested route:** `GET /persona/{persona_id}/details` — match whatever
prefix/naming convention `app/persona/persona_router.py` already uses for
similar persona-profile endpoints; don't introduce a new convention.

**Auth:** normal `Depends(get_current_user)`, like every other non-auth
route.

**Returns exactly these fields, nothing else:**
- `name`
- `desc` (persona description)
- `expertise`
- `category`
- `likes_dislikes` (likes and dislikes)

**Field sourcing** (per the current `StructuredTraits` shape described in
the design rollup §3f/§5b — confirm against `app/persona/schemas.py`):
- `expertise` → `traits.interests_expertise.expertise` (`List[str]`).
- `likes_dislikes` → `traits.likes_dislikes`.
- `name` / `desc` / `category` → likely top-level `Persona` columns rather
  than trait fields, but confirm — don't assume without checking the model.

**Edge cases to handle, not ignore:**
- `Persona.traits` can be a legacy free-text string instead of a structured
  `StructuredTraits` object (`CLAUDE.md` calls this out explicitly). If
  `traits` isn't structured, `expertise` and `likes_dislikes` should come back
  `null`/empty rather than erroring — don't let this 500.
- If `persona_id` doesn't exist, or resolves to a human persona
  (`is_human=True`) rather than an AI persona, return 404 — this endpoint is
  for AI persona profiles.

**Layering** (per `CLAUDE.md`'s strict DB-access boundary):
- Router calls a service method on `persona_service.py`.
- Service does the existing Redis read-through check first (`personas` is
  already cached, 5 min TTL, per the design rollup §5c) — cache hit returns
  immediately; miss calls into `persona_crud.py`, converts the ORM row into a
  new `PersonaDetailsResponse` Pydantic model, populates the cache on the way
  out, consistent with the existing pattern.
- Add any new query needed to `persona_crud.py` — don't inline a query in the
  service or router.
- If `category` requires a join/relation, that query also belongs in
  `persona_crud.py`.

**Response schema** — add a `PersonaDetailsResponse` model (check
`app/persona/schemas.py` for where sibling response models live) with the
five fields above.

---

## API 2 — Persona Chats List

**Purpose:** populate a list on the persona profile page of every chat
(session/fork, per the multi-fork design in the rollup §5b) the current user
has had with this persona — including blocked ones — each with a status.

**Suggested route:** `GET /persona/{persona_id}/chats` — again, match
existing router conventions rather than inventing a new URL shape.

**Auth:** `Depends(get_current_user)`. The human persona ID always comes from
the authenticated user, never from a request param — a user can only ever
list their own chats with a persona.

**Data source:** `persona_sessions` rows where `ai_persona_id = persona_id`
and `human_persona_id = current_user.id`. No new table needed — this is the
existing forking model from the rollup §5b.

### Status logic (confirmed with the requester — implement exactly this)

Three mutually exclusive statuses per chat: `recent`, `active`, `blocked`.

1. **Determine "recent" first, across ALL of the user's sessions with this
   persona (not just the current page)** — the session with the latest
   `updated_at` is `recent`. Per the rollup §5b, `updated_at` is bumped on
   every `save()`, including saves against an already-blocked session, so it
   already means "last time the user sent this persona a message" — use it
   as-is, don't derive a separate timestamp.
   - **Recent overrides blocked.** If the most-recently-messaged session is
     also blocked, it is still labeled `recent`, not `blocked` (confirmed
     with requester).
   - This means recency must be computed independently of pagination — e.g.
     a separate `ORDER BY updated_at DESC LIMIT 1` lookup for the whole set,
     not just "is this the first row of the current page." Don't let the
     "recent" tag silently disappear once the user is on page 2.
2. **Every other session** (i.e. not the single recent one): `blocked` if
   currently blocked, otherwise `active`.

### Computing "currently blocked" — read-only, no side effects

Do **not** call whatever `PersonaSession.load()`/decay path Brain uses for
live turns — that path may perform wall-clock decay and an accompanying
`save()` as a side effect (rollup §6), which is inappropriate for a plain
listing endpoint (and would mean one `GET` triggers N writes).

Confirm which of these is the current live shape of `persona_sessions` and
implement accordingly:
- If a `blocked_until` column exists (§6c — auto-expiring block): a session
  is *effectively* blocked if `is_blocked` is true **and** (`blocked_until`
  is null or still in the future relative to now). Do this as a plain
  read-only comparison in the service layer — don't mutate or save anything.
- If there's no `blocked_until` column yet (block is still permanent-only):
  just use the raw `is_blocked` column directly.

### Pagination

Confirmed with requester: paginate via `page`/`limit` query params (pick
sensible defaults, e.g. `page=1`, `limit=20`, and cap `limit` server-side to
something reasonable). Sort order: `updated_at DESC` (most recently active
chat first) — this is a reasonable default given the feature's purpose;
flag it in the PR if a different order seems more natural once you're
looking at the real data.

### Response shape (confirmed minimal — no message previews, no stats)

Each item:
- `persona_session_id` (or whatever the actual PK/identifier column is
  called — confirm)
- `status`: `"recent" | "active" | "blocked"`
- `last_updated_at` (the `updated_at` value used for the recency
  calculation)

Wrap in the pagination envelope pattern already used elsewhere in this API
(check an existing paginated endpoint, e.g. in `challenge` or `conversations`
routers, and match its shape rather than inventing a new one) — page,
limit, total count, items.

**Layering:**
- Router → a service method (in `persona_service.py`, or wherever
  session-listing logic should live per existing conventions — check if
  there's already a more specific service module for `persona_sessions`)
  → `persona_session_crud.py` for the actual queries.
- `persona_sessions` is explicitly **not** cached (rollup §5c — it mutates
  every turn, so a naive cache risks stale/lost-update reads). Don't add
  caching here even though `personas` (API 1) is cached — these are two
  different tables with different caching rules.
- Add two read functions to `persona_session_crud.py`:
  - one to fetch the single most-recent session id/timestamp for the pair
    (unpaginated, `LIMIT 1`)
  - one to fetch the paginated list for the pair + a total count
  Both are new, additive functions — don't touch the existing
  `load()`/`save()`/mutation logic in that file.

**Edge cases:**
- No sessions yet for this pair → return an empty paginated list, not a 404.
- Invalid/nonexistent `persona_id`, or `persona_id` resolves to a human
  persona → 404, same as API 1.

---

## Also required

- **Update `/docs`** for both new routes as part of this same change —
  `CLAUDE.md` requires this for every REST route addition, not as a
  follow-up.
- Add both new Pydantic response models near the other persona-related
  schemas rather than defining them inline in the router.
- No changes to `Brain`, `EmotionEngine`, or any mutation path — this task
  is purely additive read endpoints on top of existing tables.

## Out of scope for this task

- Frontend rendering of either endpoint.
- Message previews / last-message text in the chats list (explicitly
  decided against for this pass).
- The block/unblock WebSocket events or historical-cutoff feature from the
  design rollup §7/§8 — unrelated to this task, don't pull them in.
- Any change to how blocking itself is triggered or decays — this task only
  *reads* the current blocked state, it doesn't change how a session becomes
  blocked or recovers.