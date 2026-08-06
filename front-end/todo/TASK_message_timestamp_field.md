# TASK (Flutter): Read the new `timestamp` field on messages

## Context

Message objects returned by the backend — both from `GET /conversations`
(REST) and the `receive_message` Socket.IO event — now include a
`timestamp` field: when the message was actually sent/persisted on the
server, in UTC. Previously there was no way to know a message's send time
from the API response; the app had to rely on local receipt time, which is
wrong for messages loaded from history (`GET /conversations`) and can drift
from the truth even for live messages.

This is the same `Message Object` shape used everywhere messages appear, so
the new field shows up in both places automatically — no separate change
per endpoint.

Full technical reference: `/app/docs/API_DOC.md` ("Message Object" section)
and `/app/docs/socketio_server_events.md` (`receive_message` entry) in the
backend repo.

---

## What changed — exact payload shape

Every message object (from `GET /conversations`'s `messages[]` array, and
from every `receive_message` socket emit) now looks like:

```json
{
  "id": 456,
  "sender_id": 123,
  "receiver_id": 45,
  "text": "hello",
  "timestamp": "2026-08-02T14:23:01.123456+00:00",
  "image_object_name": null,
  "challenge_session_id": null,
  "persona_session_id": 5190
}
```

- `timestamp`: ISO 8601 datetime string, UTC (`+00:00` offset). This is when
  the message was persisted server-side — for AI replies, that's after
  Gemini responds, not when the user's message that triggered it was sent.

This is purely additive — no existing field was removed or renamed, so
clients that ignore the new field are unaffected.

---

## What the app should concretely do

- Parse and store `timestamp` per message instead of (or in addition to)
  any local client-side receipt time.
- Use it for message list display (e.g. "sent at" labels, day separators)
  and for chronological ordering if the app does any client-side sorting —
  `GET /conversations` already returns messages in chronological order
  server-side, so this is mainly needed for display and for messages that
  arrive live via `receive_message`.
- Convert from UTC to local time for display as usual.

---

## Testing checklist

- [ ] Load conversation history via `GET /conversations` and confirm every
      message in the response has a valid, parseable `timestamp`.
- [ ] Send a live message and confirm the `receive_message` payload (for
      both the echoed user message, if applicable, and the AI reply)
      includes a valid `timestamp`.
- [ ] Confirm message timestamps display correctly across a day boundary
      (UTC-to-local conversion) and sort/order as expected in the UI.
