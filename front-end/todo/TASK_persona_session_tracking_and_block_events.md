# TASK (Flutter): Persona session tracking + block/unblock event handling

## Context

The backend has three pieces of behavior the mobile app doesn't currently
integrate with:

1. **Persona sessions** — every AI conversation has server-side emotional
   state (`persona_session_id`, arousal/mood/rapport/etc.) attached to it.
   The app doesn't need to (and shouldn't) explicitly create this for
   normal chat — it's created automatically by the server — but it needs
   to start reading and storing `persona_session_id` from message
   payloads, because the block/unblock events below (and future features)
   are keyed on it, not on `persona_id` alone.
2. **Block/unblock events** — a persona can become temporarily
   unresponsive ("blocked") if a conversation gets too heated or the user
   repeatedly sends disallowed content. Today this is invisible to the
   client: the blocked reply arrives as an ordinary chat bubble
   indistinguishable from a normal one, and there's no way to know when
   the persona becomes responsive again short of just sending another
   message and seeing what comes back. Two new server events and one new
   client-emittable event fix this.
3. **Starting a fresh session** — previously there was no way for the app
   to explicitly start a brand-new session with a persona (e.g. so the
   user can "start over" after getting blocked, instead of waiting for
   the block to expire). A new REST endpoint fixes this.

Parts 1–2 are Socket.IO only. Part 3 is a new REST endpoint. Full
technical reference: `/app/docs/socketio_server_events.md` (Connection +
Messaging Events) and `/app/docs/API_DOC.md` (endpoint 6) in the backend
repo. This doc is the Flutter-side integration guide for the same change.

---

## Part 1 — Persona session creation (nothing to build for normal chat)

**For normal chat, there is no "create session" call to make.** Sessions
are created lazily, server-side, the first time the app sends a message
to a given persona — the server resolves (or creates, on the very first
message) a `persona_session_id` for the `(persona_id, current_user_id)`
pair automatically inside the existing `send_message` handling. Do not
add a pre-flight "start session" request before the first message in a
new chat; `send_message`'s existing payload (`sender_id`, `receiver_id`,
`text`, `image_object_name`, `challenge_session_id`) is unchanged and
already sufficient. (There IS now an explicit way to start a session —
see Part 3 — but it's for the specific "fresh start" case, not for
opening an ordinary new chat.)

**What the app does need to do:** start capturing `persona_session_id`
from every `receive_message` event and from `GET /conversations` message
history, and store it per `(persona_id, user_id)` pair (e.g. alongside
whatever local model already represents a conversation/chat thread).
`persona_session_id` is `null` for challenge-mode messages (challenges
don't use the persona emotional-state system) and populated for regular
persona chat. The app will need this stored value to correlate an
incoming `persona_blocked` event (see Part 2) with the correct chat
thread in the UI, since that event's payload only carries
`persona_session_id`, not `persona_id`.

No other client-side behavior changes for this part — just start
persisting a field that's already been in the message payload.

---

## Part 2 — Block / unblock events

### New server→client event: `persona_blocked`

Fires once, on the exact turn a persona transitions into the blocked
state — not on every subsequent message while still blocked. Delivered
to the same room as (and in addition to, not instead of) that turn's
normal `receive_message` — you'll get both events for that turn. The
`receive_message` bubble itself will contain the persona's in-character
"I'm done talking to you" reply; `persona_blocked` is the structural
signal to drive UI state off of.

```json
{
  "persona_session_id": 4821,
  "block_reason": "arousal_threshold",
  "blocked_until": "2026-07-26T18:45:00+00:00"
}
```

- `block_reason`: `"arousal_threshold"` (conversation got too heated) or
  `"repeated_content_violations"` (repeated disallowed content).
- `blocked_until`: ISO 8601 UTC timestamp — when the block auto-expires.
  Purely informational for UI purposes (e.g. "try again after ~6pm") —
  don't build a client-side countdown-and-auto-retry against this
  timestamp; see `check_unblock_status` below for the correct way to
  actually confirm unblock.

**Suggested UX:** on receipt, match `persona_session_id` against your
stored session id for the open/relevant chat thread, then disable the
message input for that persona (or show a banner/toast) with a message
derived from `block_reason`, and optionally show `blocked_until` as a
rough "try again around then" hint.

### New client→server event: `check_unblock_status`

An on-demand poll — "is this persona still blocked, right now?" There is
no server-side push/timer that tells you the moment a block expires; the
app must ask. This is a deliberate design choice on the backend (no job
scheduler in this stack), so don't wait for a server-initiated unblock
event that isn't `persona_blocked`'s counterpart below.

Emit:
```json
{ "user_id": 123, "persona_id": 45 }
```

- `user_id`: the current logged-in user's id (same value normally sent as
  `sender_id` on `send_message`).
- `persona_id`: the AI persona's id (same value normally sent as
  `receiver_id`).

If the persona is still blocked, **nothing is emitted back** — no error,
no explicit "still blocked" event. If it's no longer blocked, you'll
receive `persona_unblocked` (see below), privately, only on the socket
connection that sent the request (not broadcast to other devices/tabs the
user may have open).

**Suggested UX / polling cadence:** once the input is disabled from a
`persona_blocked` event, poll `check_unblock_status` on some reasonable
interval (e.g. every 30–60s, or when the chat screen regains foreground/
becomes visible again) rather than tightly — there's no cost-based reason
to hammer it, but there's also no server-side rate limit assumed here, so
pick an interval that feels responsive without being wasteful. Stop
polling once `persona_unblocked` is received.

### New server→client event: `persona_unblocked`

Private response to `check_unblock_status`, delivered only to the
requesting connection:

```json
{ "persona_session_id": 4821 }
```

On receipt: match `persona_session_id` against the blocked chat thread,
re-enable the message input, clear any block banner/state.

---

## Part 3 — Starting a fresh session (new REST endpoint)

New endpoint, not Socket.IO: **`POST /persona-sessions/new`**. Same auth
as every other REST endpoint (`Authorization: Bearer <google_id_token>`).

Request body:
```json
{ "persona_id": 45 }
```

Response `200 OK`:
```json
{ "persona_session_id": 5190 }
```

This creates a brand-new session with baseline (reset) emotional state
for `(persona_id, current_user_id)`, **ignoring whatever session
currently exists for that pair — including a blocked one.** It does not
wait for or clear the old block; the old blocked session row is left
exactly as it was (still blocked, still on record), and this call simply
starts an entirely new, independent one alongside it. As soon as this
call succeeds, the new session is what `send_message` will use for that
persona going forward — no separate "activate" step needed.

**When to call this:** only on explicit user action, not automatically.
The intended flow is: user receives `persona_blocked` → sees a blocked
banner/state (Part 2) → is offered a choice, e.g. "Wait for {persona} to
cool down" (poll `check_unblock_status`) vs. "Start over" (call this
endpoint). Don't call this automatically the moment a block happens —
that would silently discard the blocked conversation's history-relevant
state without the user choosing to. It's also fine to expose this as a
general "start fresh conversation" action outside the blocked-state flow
if there's a product reason to (e.g. a settings/reset button), not only
as a reaction to being blocked.

**After calling it:** update your locally stored `persona_session_id` for
that `(persona_id, user_id)` pair to the new value from the response, and
clear any blocked-state UI immediately (don't wait for a
`persona_unblocked` event — this is a synchronous REST call, the new
session isn't blocked from the moment it's created).

---

## Event/endpoint summary

| Event / Endpoint | Direction | When |
|---|---|---|
| `persona_blocked` | Socket.IO, server → client (broadcast to `user:{id}` room) | Once, on the turn a persona becomes blocked |
| `check_unblock_status` | Socket.IO, client → server | App-initiated poll while a persona is known-blocked |
| `persona_unblocked` | Socket.IO, server → client (private, requester only) | In response to `check_unblock_status`, only if no longer blocked |
| `POST /persona-sessions/new` | REST | User explicitly chooses to start a fresh session (e.g. instead of waiting out a block) |

---

## Testing checklist

- [ ] Store `persona_session_id` from `receive_message` payloads and confirm it's non-null for regular chat, null for challenge messages.
- [ ] Trigger a block (send hostile messages, or ask the backend team for a way to force one in a test environment) and confirm `persona_blocked` arrives and disables the correct chat thread's input, matched by `persona_session_id`.
- [ ] Confirm a normal `receive_message` bubble also still arrives for that same turn (the in-character refusal) — both events fire together.
- [ ] Emit `check_unblock_status` while still blocked and confirm no unexpected UI change occurs (no event should arrive).
- [ ] After the block expires (or is reset by an admin), emit `check_unblock_status` again and confirm `persona_unblocked` re-enables input.
- [ ] Confirm `persona_unblocked` does NOT arrive on a second device/session logged into the same account that didn't itself send `check_unblock_status` (it's private, not broadcast).
- [ ] While blocked, call `POST /persona-sessions/new` and confirm the response returns a different `persona_session_id` than the blocked one, and that sending a new message to that persona now gets a normal (non-blocked) reply.
- [ ] After calling `POST /persona-sessions/new`, confirm the persona's emotional "feel" is genuinely reset (e.g. a previously-heated conversation now starts calm) rather than carrying over the old session's state.
