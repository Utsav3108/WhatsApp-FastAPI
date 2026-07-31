# TASK (Flutter): Persona details page — two new REST endpoints

## Context

Two new read-only endpoints back a persona details/profile page: static
profile info (name, description, expertise, category, likes/dislikes), and a
paginated list of every chat ("fork" — see the persona-session doc below if
this term is new) the current user has had with that persona, each tagged
with a status so the UI can show recent/active/blocked chats differently.

Both are `GET` requests, same auth as every other REST call
(`Authorization: Bearer <google_id_token>`). Full technical reference:
`/app/docs/API_DOC.md` (endpoints 6 and 7) in the backend repo.

---

## Endpoint 1 — `GET /personas/{persona_id}/details`

Call this when the persona details page loads, using the AI persona's id.

Response `200 OK`:
```json
{
  "name": "Donald Trump",
  "desc": "45th and 47th President of the United States.",
  "expertise": ["Real Estate", "Negotiation", "Media"],
  "category": "Historical Figure",
  "likes_dislikes": {
    "likes": ["Winning", "Loyalty"],
    "dislikes": ["Losing", "Fake news"]
  }
}
```

- `expertise` and `likes_dislikes` can both come back `null` — this happens
  for personas whose backing data predates the structured-traits format.
  Treat `null` as "nothing to show" (hide that section of the UI), not as an
  error or loading state.
- `404 Not Found` if `persona_id` doesn't exist, or refers to a human user
  account rather than an AI persona (shouldn't normally happen from a details
  page reached by tapping an AI persona, but handle it as a generic "persona
  not found" state rather than crashing).

---

## Endpoint 2 — `GET /personas/{persona_id}/chats`

Call this to populate a "your chats with this persona" list on the same
details page.

Query params: `page` (default `1`), `limit` (default `20`, max `100`).

```
GET /personas/45/chats?page=1&limit=20
```

Response `200 OK`:
```json
{
  "chats": [
    { "persona_session_id": 5190, "status": "recent", "last_updated_at": "2026-07-27T10:15:00+00:00" },
    { "persona_session_id": 4821, "status": "blocked", "last_updated_at": "2026-07-20T18:45:00+00:00" },
    { "persona_session_id": 4310, "status": "active", "last_updated_at": "2026-07-10T09:00:00+00:00" }
  ],
  "page": 1,
  "limit": 20,
  "total_count": 3,
  "total_pages": 1,
  "has_more": false
}
```

- Always scoped to the current logged-in user — there's no way to pass a
  different user id, and there's no need to.
- `status` is exactly one of `"recent"`, `"active"`, `"blocked"`:
  - Exactly one chat in the *entire* set (not just the current page) is
    `"recent"` — the one the user messaged most recently. If that
    most-recently-messaged chat happens to also be blocked, it's still shown
    as `"recent"`, not `"blocked"` — recency wins. Don't compute your own
    "most recent" client-side from the page you have; trust the `status`
    field, since the actual most-recent chat might be on a different page
    than the one you're currently viewing.
  - Every other chat is `"blocked"` if currently blocked, else `"active"`.
- `persona_session_id` is the same id used elsewhere (e.g.
  `GET /conversations?persona_session_id=...`, from the existing
  persona-session-tracking work) — tapping a row in this list to open its
  history should use that endpoint with this id.
- No message preview/last-message text is included in this response by
  design — if the design calls for a preview snippet, that's explicitly out
  of scope for this endpoint and would need a separate follow-up.
- Empty state: if the user has never chatted with this persona, you get
  `{ "chats": [], "page": 1, "limit": 20, "total_count": 0, "total_pages": 1, "has_more": false }`
  — not a 404.
- `404 Not Found` — same conditions as endpoint 1 (bad/human `persona_id`).

---

## Endpoint summary

| Endpoint | When |
|---|---|
| `GET /personas/{persona_id}/details` | Persona details page load |
| `GET /personas/{persona_id}/chats?page=&limit=` | Populating the "your chats with this persona" list on the same page, paginating as the user scrolls |

---

## Testing checklist

- [ ] `GET /personas/{id}/details` for a persona with structured traits shows expertise and likes/dislikes correctly.
- [ ] Same call for an older/legacy persona (or ask backend for a test id) returns `expertise`/`likes_dislikes` as `null` and the UI hides those sections gracefully instead of erroring.
- [ ] Calling either endpoint with a bad/nonexistent `persona_id`, or a human user's id, returns `404` and the UI shows a reasonable "not found" state.
- [ ] `GET /personas/{id}/chats` for a persona with multiple chats shows exactly one `"recent"` row, with the rest split between `"active"`/`"blocked"` correctly.
- [ ] Force a chat to be both blocked AND the most-recently-messaged one (e.g. get blocked mid-conversation, don't start a new session afterward) and confirm it still shows as `"recent"`, not `"blocked"`, in the list.
- [ ] Page through multiple pages of chats (if a test account has >20) and confirm `has_more`/`total_pages` are respected and pagination doesn't cause the `"recent"` chat to disappear if it falls on a page you're not currently viewing.
- [ ] A persona with zero chats returns an empty list, not a 404 or error state.
