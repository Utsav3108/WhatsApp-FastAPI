# TASK: `check_unblock_status` now always replies (ack callback)

## Context

`check_unblock_status` is the Socket.IO event a client emits to ask "is
this persona session still blocked, right now?" (e.g. on chat screen
mount, on reconnect, or on a poll while blocked). Previously it only
replied when the session had actually become unblocked — a private
`persona_unblocked` emit. If the session was still blocked, or the
`persona_session_id` sent didn't belong to the `(persona_id, user_id)`
pair, the server replied with **nothing at all**, both cases looking
identical (silence) from the client's side. Any client had to guess by
racing a timeout against `persona_unblocked` and assuming "still blocked"
if nothing arrived in time.

The server now always replies to the requesting client via a Socket.IO
**ack callback** — no new event name, no room/broadcast semantics, just a
direct reply to the socket that made the call. This removes the need for
any client-side timeout guess.

Full technical reference: `/app/docs/socketio_server_events.md` (Connection
Events → `check_unblock_status`) in the backend repo.

---

## What changed

**Before:** `socket.emit("check_unblock_status", payload)` — fire and
forget, then separately listen for a `persona_unblocked` event that may or
may not arrive.

**Now:** emit with a callback and read the ack directly:

```js
socket.emit("check_unblock_status", payload, (response) => {
  // response is always present now
});
```

The `payload` shape is unchanged: `{ user_id, persona_id, persona_session_id? }`.

## New response shapes (the ack callback argument)

- **Still blocked:**
  ```json
  { "blocked": true, "persona_session_id": 123, "block_reason": "arousal_threshold", "blocked_until": "2026-08-06T18:00:00Z" }
  ```
- **No longer blocked:**
  ```json
  { "blocked": false, "persona_session_id": 123 }
  ```
  The server also still emits `persona_unblocked` privately (same shape as
  before, `{ "persona_session_id": 123 }`) alongside this ack, unchanged —
  existing listeners for it keep working during migration, so this can be
  a non-breaking rollout if useful.
- **Payload missing `user_id`/`persona_id`:**
  ```json
  { "error": "invalid_payload" }
  ```
- **`persona_session_id` doesn't belong to the `(persona_id, user_id)`
  pair, or doesn't exist:**
  ```json
  { "error": "not_found" }
  ```

## What the client concretely needs to do

1. Switch every `check_unblock_status` emit from
   `socket.emit(event, payload)` to `socket.emit(event, payload, callback)`
   and resolve state directly from `callback`'s `blocked` / `error` field,
   instead of listening for `persona_unblocked` and racing a timeout
   against it.
2. Drop the client-side grace-period timeout that was standing in for a
   real reply (e.g. the web client's `CHECK_GRACE_MS` in
   `useBlockState.js`) — the ack itself is now the timing signal, so
   there's nothing to race.
3. Handle the two error cases explicitly rather than treating them the
   same as "still blocked": `invalid_payload` indicates a client bug (bad
   payload), `not_found` indicates the referenced `persona_session_id` is
   stale/wrong and the client should probably re-resolve which session is
   actually active rather than keep polling the same id.
