# Socket.IO Server Events Documentation

This document describes the Socket.IO events handled by the backend server in `socketio_server.py`. Use this as a reference for integrating with the mobile client.

---

## Connection Events

### `connect`
- **Description:** Triggered when a client connects to the Socket.IO server.
- **Payload:** None
- **Response:** None

### `disconnect`
- **Description:** Triggered when a client disconnects from the server.
- **Payload:** None
- **Response:** None

### `join`
- **Description:** Associates a socket session with a user ID.
- **Payload:** `{ "user_id": int }`
- **Response:** None

### `check_unblock_status`
- **Description:** On-demand poll for whether a persona session that was previously blocked (arousal threshold or repeated content violations) has since auto-unblocked. Reuses the same lazy unblock-on-load logic as a normal chat turn — no server-side timer/scheduler involved. Always acks the requesting client with the result (Socket.IO ack callback) — emit with a callback to receive it: `socket.emit("check_unblock_status", payload, callback)`.
- **Payload:**
  - `user_id`: int
  - `persona_id`: int
  - `persona_session_id`: int (optional) — pins the poll to this specific fork. If omitted, the server resolves the most-recently-updated fork for the `(persona_id, user_id)` pair (unchanged legacy behavior). If provided and it doesn't belong to this pair (or doesn't exist), the ack returns `{"error": "not_found"}`.
- **Response:** ack callback, always sent to the requesting client only:
  - Still blocked: `{"blocked": true, "persona_session_id": int, "block_reason": string, "blocked_until": string (ISO 8601)}`
  - No longer blocked: `{"blocked": false, "persona_session_id": int}` — the server also still emits `persona_unblocked` privately (room=sid) in this case, unchanged, for existing listeners.
  - `user_id`/`persona_id` missing from the payload: `{"error": "invalid_payload"}`
  - `persona_session_id` doesn't belong to the pair, or doesn't exist: `{"error": "not_found"}`

### `leave_chat`
- **Description:** Cancels the in-flight background Gemini task for a specific chat (persona chat or challenge), e.g. when the user navigates away before the AI reply completes.
- **Payload:**
  - `user_id`: int
  - `persona_id`: int (optional) — for regular persona chats
  - `challenge_session_id`: int (optional) — for challenge chats
  - `persona_session_id`: int (optional) — pins the cancellation to this specific fork. If omitted, the server resolves the most-recently-updated fork for the `(persona_id, user_id)` pair (unchanged legacy behavior). If provided and it doesn't belong to this pair (or doesn't exist), the cancellation is skipped (no task is cancelled).
- **Response:** None

---

## Challenge Events


### `join_challenge`
- **Description:** Joins a socket to a challenge room for group communication. The server will add the socket to a room named `challenge:<challenge_session_id>`.
- **Payload:** `{ "challenge_session_id": int }`
- **Response:** None


### `challenge_completed`
- **Description:** (Emitted by server) Notifies all clients in a challenge room about the updated status of a challenge session (e.g., completed, failed, etc.).
- **Payload:**
  - `reason` (string, optional): Reason for challenge completion or status change
  - `challenge_status` (ChallengeResult): Status of the challenge (e.g., "COMPLETED", "FAILED", "ACTIVE")
  - `challenge_session_id` (int): The session ID for the challenge
  - `user_id` (int): The user who completed or is involved in the challenge
  - `challenge_id` (int): The challenge ID

---

## ChallengeResult Values

| Value                     | Description                                             |
| ------------------------- | ------------------------------------------------------- |
| `won`                     | Challenge completed successfully.                       |
| `won_objective_completed` | Persona agreed to or completed the challenge objective. |
| `lost_timeout`            | Challenge failed due to timeout or inactivity.          |
| `lost_rejected`           | Persona explicitly rejected the challenge objective.    |
| `lost_blocked`            | Persona became angry or blocked the user.               |
| `lost_rule_violation`     | User violated challenge rules or restrictions.          |
| `abandoned`               | Challenge was abandoned before completion.              |
| `active`                  | Challenge is currently active and ongoing.              |

---

## Messaging Events


### `send_message`
- **Description:** Sends a message from a user to a persona (or another user) within a challenge session. Triggers Gemini AI response in the background. The server will also update message history and cache.
- **Payload:**
  - `sender_id`: int
  - `receiver_id`: int
  - `text`: str
  - `challenge_session_id`: int
  - `image_object_name`: str (optional)
  - `persona_session_id`: int (optional) — pins the message to this specific fork of the `(receiver_id, sender_id)` persona chat. If omitted, the server resolves/auto-creates the most-recently-updated fork for that pair (unchanged legacy behavior). If provided and it doesn't belong to that pair (or doesn't exist), the message is silently dropped — nothing is persisted, no `receive_message` is emitted.
- **Response:** None (AI response will be sent via `receive_message` event)


### `receive_message`
- **Description:** (Emitted by server) Delivers a message (AI or user) to all clients in the challenge room.
- **Payload:**
  - `id` (int): Message ID
  - `sender_id` (int): Sender user ID
  - `receiver_id` (int): Receiver user ID
  - `text` (string): Message text
  - `timestamp` (datetime, ISO 8601, UTC): When the message was sent/persisted
  - `image_object_name` (string, optional): Name of the image object if present
  - `challenge_session_id` (int, optional): Challenge session ID if message is part of a challenge
  - `persona_session_id` (int, optional): The persona session this message belongs to (regular chat only, `null` for challenges). Clients may optionally set this on `send_message` to target a specific fork; if omitted there, the server resolves it via the pair's most-recently-updated fork as before. Either way, read it here to track the active session for a given (persona, user) pair.


### `persona_blocked`
- **Description:** (Emitted by server) Fires on the exact turn a persona session transitions into the blocked state (arousal threshold or repeated content violations) — not on subsequent turns while already blocked. Emitted to the same room as, and alongside, that turn's `receive_message` (the in-character canned refusal) — these are two independent signals, not a replacement for one another.
- **Payload:**
  - `persona_session_id` (int): The persona session that just became blocked
  - `block_reason` (string): `"arousal_threshold"` or `"repeated_content_violations"`
  - `blocked_until` (string, ISO 8601): When the block auto-expires

### `persona_unblocked`
- **Description:** (Emitted by server, private) Notifies a single requesting client, in response to `check_unblock_status`, that a persona session is no longer blocked. Never broadcast to the room.
- **Payload:**
  - `persona_session_id` (int): The persona session that is now unblocked


---



## Notes
- All events are asynchronous.
- Rooms are used for challenge sessions: `challenge:<challenge_session_id>`.
- The server may emit additional events for challenge status (e.g., timeout/loss) as needed.
- The server manages user-to-socket mapping and message caching for performance.
- All event payloads are fully described above for mobile integration.
