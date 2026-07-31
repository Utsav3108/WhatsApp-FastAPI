# TASK (Flutter): Send `persona_session_id` on socket events that act on a chat

## Context

Three Socket.IO events the app already emits — `send_message`, `leave_chat`,
and `check_unblock_status` — currently have the server guess which
`persona_session_id` ("fork" of a persona conversation) they apply to, by
always resolving "the most-recently-updated fork for this
`(persona_id, user_id)` pair." This is a problem once more than one fork can
exist for the same pair — e.g. after using "start fresh conversation"
(`POST /persona-sessions/new`, see the prior task doc,
`TASK_persona_session_tracking_and_block_events.md`, Part 3), or if the same
account is open on two devices/tabs on different forks — because the
server's guess can silently point at the wrong fork.

All three events now accept an **optional** `persona_session_id` field. If
the app already knows the `persona_session_id` for the chat thread it's
acting on (which it should, per Part 1 of the prior task doc — it's already
being captured from `receive_message` and `GET /conversations`), it should
start sending it on these three events. Nothing changes for chats where the
app hasn't learned a `persona_session_id` yet (e.g. a brand-new chat with no
messages sent) — omitting the field keeps today's behavior exactly as-is.

Full technical reference: `/app/docs/socketio_server_events.md` (`send_message`,
`leave_chat`, `check_unblock_status` entries) in the backend repo.

---

## What changed — exact payload shapes

### `send_message`

```json
{
  "sender_id": 123,
  "receiver_id": 45,
  "text": "hello",
  "image_object_name": null,
  "challenge_session_id": null,
  "persona_session_id": 5190
}
```

- `persona_session_id` (optional): the fork this message belongs to.
- **If omitted:** unchanged legacy behavior — server resolves/auto-creates
  the most-recently-updated fork for `(receiver_id, sender_id)`.
- **If provided but it doesn't belong to `(receiver_id, sender_id)`** (wrong
  pair, or the id doesn't exist): **the message is silently dropped.**
  Nothing is persisted, no `receive_message` comes back, no error is
  emitted. This is a deliberate reject, not a fallback to a different fork —
  don't rely on the server "fixing" a stale/wrong id for you.

### `leave_chat`

```json
{ "user_id": 123, "persona_id": 45, "persona_session_id": 5190 }
```

- `persona_session_id` (optional): the fork whose in-flight Gemini reply
  should be cancelled.
- **If omitted:** unchanged legacy behavior — server resolves the
  most-recently-updated fork for `(persona_id, user_id)`.
- **If provided but mismatched:** the cancellation is silently skipped (no
  task is cancelled) — same reject-not-fallback rule as above.

### `check_unblock_status`

```json
{ "user_id": 123, "persona_id": 45, "persona_session_id": 5190 }
```

- `persona_session_id` (optional): the fork being polled for unblock status.
- **If omitted:** unchanged legacy behavior — server resolves the
  most-recently-updated fork for `(persona_id, user_id)`.
- **If provided but mismatched:** nothing is emitted back — indistinguishable
  from "still blocked" from the client's perspective.

---

## What the app should concretely do

Once `persona_session_id` is known for a chat thread (already being tracked
per the prior task doc), start including it on every `send_message`,
`leave_chat`, and `check_unblock_status` emit for that thread. If the app
hasn't yet learned the id for a brand-new chat (no messages sent to this
persona yet), it's fine to omit the field — the fallback behavior covers
that case exactly as it does today.

**Do not** send a stale or guessed `persona_session_id` (e.g. left over from
before a "start fresh conversation" reset) — since a mismatched id now
silently drops the action instead of falling back, sending the wrong one is
worse than omitting it entirely. Make sure the locally stored
`persona_session_id` is updated immediately after
`POST /persona-sessions/new` succeeds (per the prior task doc, Part 3)
before it's used on these events again.

---

## Testing checklist

- [ ] Send a message with the correct, currently-active `persona_session_id` and confirm normal behavior (message appears, AI reply arrives via `receive_message`).
- [ ] Send a message with a deliberately wrong/stale `persona_session_id` (e.g. one from a different persona, or from before a "start fresh" reset) and confirm nothing comes back — no message appears, no reply, no error.
- [ ] Send a message omitting `persona_session_id` entirely and confirm unchanged legacy behavior (still works exactly as before this change).
- [ ] Emit `leave_chat` with the correct `persona_session_id` while a reply is in-flight and confirm the in-flight reply is cancelled as before.
- [ ] Emit `leave_chat` with a mismatched `persona_session_id` and confirm the in-flight reply is NOT cancelled (task keeps running to completion).
- [ ] Emit `check_unblock_status` with the correct `persona_session_id` on an unblocked session and confirm `persona_unblocked` still arrives normally.
- [ ] Emit `check_unblock_status` with a mismatched `persona_session_id` and confirm nothing is emitted back.
