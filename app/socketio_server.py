from datetime import datetime
from typing import Optional
import os
import traceback

from fastapi import Depends
import socketio
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app import enums
from app.AppServices.connection_manageer import ConnectionManager
import app.schemas as schemas
import app.crud as crud
import app.cache as cache
from app.gemini import ask_gemini, evaluate_challenge
from app.database import SessionLocal
from app.services import challenge_service, challenge_session
from app.schemas import ChallengeCompletion

from app.enums import ChallengeResult

from app.services import message_service
from app.persona import persona_service, persona_session_crud
from app.persona.persona_session import PersonaSession


# Socket.IO server setup with optional Redis support
redis_url = os.getenv("REDIS_URL")
if redis_url:
  # print(f"Connecting Socket.IO to Redis at {redis_url}")
    client_manager = socketio.AsyncRedisManager(redis_url)
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', client_manager=client_manager)
else:
  # print("Using in-memory Socket.IO manager.")
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

sio_app = socketio.ASGIApp(sio)
manager = ConnectionManager()

# Track in-flight Gemini background tasks so we can cancel them on leave/disconnect
_background_tasks: dict[str, asyncio.Task] = {}  # chat_key -> asyncio.Task


# --------------------------------------------------------------------------
# Connection Events
# --------------------------------------------------------------------------

@sio.event
def connect(sid, environ):
  # print(f"Socket.IO: {sid} connected")
  pass


@sio.event
async def disconnect(sid):
    print(f"Socket.IO: disconnect called for sid {sid}")
    session = await sio.get_session(sid)
    if session:
        user_id = session.get("user_id")
        print(f"Socket.IO: disconnect session user_id found: {user_id}")
        if user_id:
            # Cancel all in-flight Gemini tasks for this user
            prefix = f"user_{user_id}_"
            keys_to_cancel = [k for k in _background_tasks if k.startswith(prefix)]
            for k in keys_to_cancel:
                task = _background_tasks.pop(k, None)
                if task and not task.done():
                    task.cancel()
                    print(f"Cancelled in-flight task for: {k}")

            from app.gemini import clear_user_active_chats
            clear_user_active_chats(user_id)

@sio.event
async def leave_chat(sid, data):
    print(f"Socket.IO: leave_chat received with data: {data}")
    user_id = data.get("user_id")
    persona_id = data.get("persona_id")
    challenge_session_id = data.get("challenge_session_id")
    if user_id:
        # Cancel in-flight Gemini task for this specific chat
        if challenge_session_id:
            chat_key = f"user_{user_id}_session_{challenge_session_id}"
        elif persona_id:
            # Mirrors handle_send_message's persona_session-keyed chat_key —
            # resolve the same most-recent session id for this pair so the
            # cancellation lookup actually matches.
            async with SessionLocal() as db:
                persona_session_id = await persona_session_crud.get_latest_persona_session_id(
                    db, ai_persona_id=persona_id, human_persona_id=user_id
                )
            chat_key = f"user_{user_id}_persona_session_{persona_session_id}" if persona_session_id is not None else None
        else:
            chat_key = None

        if chat_key:
            task = _background_tasks.pop(chat_key, None)
            if task and not task.done():
                task.cancel()
                print(f"Cancelled in-flight task for: {chat_key}")

        # from app.gemini import clear_active_chat
        # clear_active_chat(user_id, persona_id=persona_id, challenge_session_id=challenge_session_id)

@sio.event
async def join(sid, data):
    user_id = data.get("user_id")
    if user_id is not None:
        await sio.save_session(sid, {"user_id": user_id})
        # Join a user-specific room for real-time persona chats
        await sio.enter_room(sid, f"user:{user_id}")
      # print(f"User {user_id} joined room user:{user_id}")


@sio.event
async def check_unblock_status(sid, data):
    """
    On-demand poll: "is this persona still blocked, right now." Reuses
    PersonaSession.load()'s existing lazy unblock-on-load logic entirely —
    no new unblock logic here, no save() (nothing needs persisting; the
    next real turn's save() will reflect the cleared state). Emits
    'persona_unblocked' privately to the requesting client only (room=sid)
    when no longer blocked; emits nothing if still blocked.
    """
    user_id = data.get("user_id")
    persona_id = data.get("persona_id")
    if not user_id or not persona_id:
        return

    async with SessionLocal() as db:
        session = await PersonaSession.load(
            db, ai_persona_id=persona_id, human_persona_id=user_id
        )

    if not session.is_blocked:
        await sio.emit(
            "persona_unblocked",
            {"persona_session_id": session.session_id},
            room=sid,
        )


@sio.event
async def join_challenge(sid, data):
  # print(f"Received join_challenge event with data: {data}")

    challenge_session_id = data.get("challenge_session_id")
    if not challenge_session_id:
      # print("no challenge_session_id provided in join_challenge event")  
        return
    
    room = f"challenge:{challenge_session_id}"
  # print(f"Joining room {room} for sid {sid}")

    await sio.enter_room(sid, room)
  # print(f"{sid} joined {room}")

async def complete_challenge(sid, user_id, challenge_id, challenge_session_id, eval: schemas.EvaluationResponse):
    if not challenge_session_id:
      # print("no challenge_session_id provided in complete_challenge event")  
        return
    
    async with SessionLocal() as db:
      # print("challenge_session_id : ", challenge_session_id)
      # print("challenge_id : ", challenge_id)
      # print("user_id : ", user_id)
      # print("eval : ", eval)
      # print("eval.status : ", eval.status)
      # print("eval.reasoning : ", eval.reasoning)

        session_details = schemas.ChallengeCompletion(
            challenge_session_id=challenge_session_id,
            challenge_status=eval.status,
            reason=eval.reasoning,
            user_id=user_id,
            challenge_id=challenge_id
        )

      # print("updating challenge session status in DB...")
        try:
            result = await challenge_session.complete_challenge_session(
                db,
                challenge_details=session_details
            )

          # print("Challenge session updated in DB with result: ", result)
          # print("Emitting challenge_completed event to client with result: ", result.model_dump_json())

          # print("Challenge session updated. Sending completion event to client... ")
            await sio.emit(
                "challenge_completed",
                result.model_dump_json(),
                room=f"challenge:{challenge_session_id}"    
            )

            room = f"challenge:{session_details.challenge_session_id}"
            await sio.leave_room(sid, room)

        except Exception as e:
            await db.rollback()
          # print(f"Error in complete_challenge event: {e}")
            traceback.print_exc()

@sio.on('complete_challenge')
async def handle_complete_challenge(sid, data):
    """
    Handle challenge completion events emitted directly by the client (e.g. on timeout).
    """
  # print(f"Socket.IO: Received complete_challenge event with data: {data}")
    challenge_session_id = data.get("challenge_session_id")
    status = data.get("status")
    reason = data.get("reason", "")
    
    if not challenge_session_id:
      # print("no challenge_session_id provided in complete_challenge event")
        return
        
    async with SessionLocal() as db:
        session = await crud.get_challenge_session_by_id(db, challenge_session_id)
        if not session:
          # print(f"Challenge session {challenge_session_id} not found in DB")
            return
            
        eval_response = schemas.EvaluationResponse(
            status=status,
            reasoning=reason
        )
        
        await complete_challenge(
            sid=sid,
            user_id=session.user_id,
            challenge_id=session.challenge_id,
            challenge_session_id=challenge_session_id,
            eval=eval_response
        )

# --------------------------------------------------------------------------
# Message Events
# --------------------------------------------------------------------------

@sio.event
async def send_message(sid, payload):
    """
    Create a new database session for this Socket.IO event and ensure it is
    always closed, even if an exception occurs.
    """
    async with SessionLocal() as db:
        try:
            await handle_send_message(payload, db, sid)
        except Exception as e:
            await db.rollback()
          # print(f"Error in send_message: {e}")
            traceback.print_exc()
            raise


async def handle_send_message(payload, db: AsyncSession, sid):
    message_in = schemas.MessageCreate(**payload)

  # print(
    #     f"Received message from user {message_in.sender_id} "
    #     f"to persona {message_in.receiver_id}: {message_in.text}"
    # )

    challenge_session = await crud.get_challenge_session_by_id(db, message_in.challenge_session_id)

    challenge = None
    if challenge_session:
        if challenge_session.status != 'active':
          # print(f"Challenge session {challenge_session.id} is not active (status: {challenge_session.status}). Ignoring message.")
            return

        from app.services import challenge_service
        challenge = await challenge_service.get_challenge_by_id(db, challenge_session.challenge_id)
        if challenge and challenge.estimated_duration_minutes:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            delta = (now - challenge_session.last_resumed_at).total_seconds() if challenge_session.last_resumed_at else 0
            total_elapsed = challenge_session.elapsed_seconds + delta
            if total_elapsed >= challenge.estimated_duration_minutes * 60:
              # print(f"Challenge session {challenge_session.id} has timed out. Completing as lost.")
                from app.services.challenge_session import complete_challenge_session
                result = await complete_challenge_session(db, schemas.ChallengeCompletion(
                    challenge_session_id=challenge_session.id,
                    challenge_status="lost_timeout",
                    reason="You ran out of time before completing the challenge.",
                    user_id=challenge_session.user_id,
                    challenge_id=challenge_session.challenge_id
                ))
                await sio.emit(
                    "challenge_completed",
                    result.model_dump_json(),
                    room=f"challenge:{challenge_session.id}"
                )
                return

    # Regular (non-challenge) chat: resolve the persona_sessions row for this
    # (ai_persona, human_persona) pair up front. If this is the pair's
    # first-ever message, save() immediately to create the row — this
    # guarantees chat_key and both the user's message and the AI's reply
    # can be stamped with a real session id, no fallback branch needed.
    # Challenges are out of scope for Brain/PersonaSession (see CLAUDE.md);
    # persona_session stays None for them, matching ask_gemini's contract.
    persona_session: Optional[PersonaSession] = None
    if not challenge_session:
        persona_session = await PersonaSession.load(
            db,
            ai_persona_id=message_in.receiver_id,
            human_persona_id=message_in.sender_id,
        )
        if persona_session.session_id is None:
            # Pure identity creation — Brain.build() hasn't run yet, so
            # nothing has mutated arousal/patience/mood this turn.
            await persona_session.save(db, state_changed=False)
        message_in.persona_session_id = persona_session.session_id

    # Save user's message
    raw_message = await crud.create_message(db, message_in)
    message = schemas.MessageResponse.model_validate(raw_message)

    past_messages = []

    if challenge_session:
        # Fetch last 11 messages (10 history + current user message)
        db_history = await message_service.get_message_by_session_id(db, challenge_session.id, limit=11)
        past_messages = [m for m in db_history if m.id != message.id]

    else:
        # Fetch last 11 messages (10 history + current user message), scoped
        # to this persona_session (fork) rather than the raw sender/receiver
        # pair — so history from a different fork (e.g. a blocked session
        # the user started fresh from via PersonaSession.create_new()) never
        # leaks into this fork's Gemini context.
        past_messages = await message_service.get_messages_by_persona_session_id(
            db, persona_session.session_id, limit=11
        )
        past_messages = [m for m in past_messages if m.id != message.id]

    # Build the chat_key so we can track the background task. Keying on the
    # resolved persona_session id (rather than the old receiver_id-based
    # key) fixes cross-fork collisions: two forks of the same
    # (sender, receiver) pair used to collapse onto the same key and cancel
    # each other's in-flight replies.
    chat_key = (
        f"user_{message_in.sender_id}_session_{challenge_session.id}" if challenge_session
        else f"user_{message_in.sender_id}_persona_session_{persona_session.session_id}"
    )

    # Cancel any previous in-flight task for the same chat to avoid parallel Gemini calls
    prev_task = _background_tasks.pop(chat_key, None)
    if prev_task and not prev_task.done():
        prev_task.cancel()

    if challenge_session:
        task = asyncio.create_task(
            handle_gemini_response(message, past_messages, sid, challenge, challenge_session.id)
        )
    else:
        task = asyncio.create_task(
            handle_gemini_response(message, past_messages, sid, persona_session=persona_session)
        )

    # Store the task reference so leave_chat / disconnect can cancel it
    _background_tasks[chat_key] = task

    # Auto-cleanup when the task finishes
    def _on_done(t, key=chat_key):
        _background_tasks.pop(key, None)
    task.add_done_callback(_on_done)


async def handle_gemini_response(message: schemas.MessageCreate, past_messages, sid, challenge: Optional[schemas.ChallengeResponse] = None, challenge_session_id=None, persona_session: Optional[PersonaSession] = None):
    """
    Background task. DB sessions are opened only for brief read/write windows;
    both Gemini calls (ask_gemini, evaluate_challenge) run with no session held.
    persona_session was already loaded by handle_send_message (regular chat
    only) — update()/compile_prompt() mutate it in-memory during PHASE 2
    below (no DB session held), and it's persisted in PHASE 3's write window.
    """
    try:
        # ---------- PHASE 1: READS ----------
        async with SessionLocal() as db:
            persona = await persona_service.get_persona_by_id(db, message.receiver_id)

            try:

                user_persona = await persona_service.get_persona_by_id(db, message.sender_id)
                user_name = user_persona.name if user_persona else "User"
            except ValueError:
                user_persona = None
                user_name = "User"

            attempt = None
            if challenge:

                attempt = await challenge_service.get_attempt_number(db, challenge.id, message.sender_id)
        # connection released

        # ---------- PHASE 2: GEMINI CALL #1 (no session held) ----------

        gemini_response_in = await ask_gemini(
            message.text,
            persona,
            persona_session=persona_session,
            user_name=user_name,
            user_role=user_persona.role if user_persona else None,
            user_bio=user_persona.bio if user_persona else None,
            senderId=message.sender_id,
            past_messages=past_messages,
            challenge=challenge,
            challenge_session_id=challenge_session_id,
            attempt=attempt
        )

        # ---------- PHASE 3: WRITE THE MESSAGE (short session) ----------
        async with SessionLocal() as db:
            try:
                gemini_message = await crud.create_message(db, gemini_response_in)
                validated_gemini_response = schemas.MessageResponse.model_validate(gemini_message)

                if persona_session is not None:
                    # Persist this turn's mutated state (update()/
                    # compile_prompt() ran in-memory during PHASE 2, no DB
                    # session held). turn_state_mutated is True only if
                    # update()/register_violation() actually ran this turn
                    # (normal turn, or harmful/sexual-content violation) —
                    # False for the hard-gate short-circuit and the
                    # language-check early return in Brain.build(), neither
                    # of which touch arousal/patience/mood/curiosity.
                    # updated_at still bumps unconditionally either way, so
                    # a poked-but-untouched session still ranks correctly
                    # as "most recent" for fork selection.
                    await persona_session.save(db, state_changed=persona_session.turn_state_mutated)

                is_session_active = True
                if challenge and challenge_session_id:
                    session = await crud.get_challenge_session_by_id(db, challenge_session_id)
                    if session and session.status != 'active':
                        is_session_active = False
            except Exception:
                await db.rollback()
                traceback.print_exc()
                return
        # connection released

        # ---------- EMIT + UPDATE IN-MEMORY HISTORY (no DB needed) ----------

        room = (
            f"challenge:{message.challenge_session_id}"
            if message.challenge_session_id
            else f"user:{validated_gemini_response.receiver_id}"
        )

        await sio.emit(
            "receive_message",
            validated_gemini_response.model_dump_json(),
            room=room
        )

        if persona_session is not None and persona_session.just_blocked:
            await sio.emit(
                "persona_blocked",
                {
                    "persona_session_id": persona_session.session_id,
                    "block_reason": persona_session.block_reason,
                    "blocked_until": persona_session.blocked_until.isoformat(),
                },
                room=room,
            )


        past_messages.append(message)
        past_messages.append(validated_gemini_response)

        # ---------- PHASE 4: GEMINI CALL #2 — EVALUATION (no session held) ----------
        if challenge and is_session_active:
            eval: schemas.EvaluationResponse = await evaluate_challenge(
                challenge,
                past_messages,
                persona,
                user_name=user_name,
                user_id=message.sender_id
            )

            if eval.status != ChallengeResult.ACTIVE:
                # complete_challenge presumably opens its own short-lived session internally
                asyncio.create_task(
                    complete_challenge(sid, message.sender_id, challenge.id, challenge_session_id, eval)
                )

    except Exception:
        traceback.print_exc()
