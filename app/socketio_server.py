from typing import Optional
import os
import traceback

from fastapi import Depends
import socketio
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import enums
from app.AppServices.connection_manageer import ConnectionManager
import app.schemas as schemas
import app.crud as crud
import app.cache as cache
from app.gemini import ask_gemini, evaluate_challenge
from app.database import SessionLocal
from app.services import challenge_service, challenge_session, persona_service
from app.schemas import ChallengeCompletion

from app.enums import ChallengeResult

from app.services import message_service, challenge_session as challenge_session_service


# Socket.IO server setup with optional Redis support
redis_url = os.getenv("REDIS_URL")
if redis_url:
    print(f"Connecting Socket.IO to Redis at {redis_url}")
    client_manager = socketio.AsyncRedisManager(redis_url)
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', client_manager=client_manager)
else:
    print("Using in-memory Socket.IO manager.")
    sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

sio_app = socketio.ASGIApp(sio)
manager = ConnectionManager()


# --------------------------------------------------------------------------
# Connection Events
# --------------------------------------------------------------------------

@sio.event
def connect(sid, environ):
    print(f"Socket.IO: {sid} connected")


@sio.event
def disconnect(sid):
    print(f"Socket.IO: {sid} disconnected")

@sio.event
async def join(sid, data):
    user_id = data.get("user_id")
    if user_id is not None:
        await sio.save_session(sid, {"user_id": user_id})
        # Join a user-specific room for real-time persona chats
        await sio.enter_room(sid, f"user:{user_id}")
        print(f"User {user_id} joined room user:{user_id}")


@sio.event
async def join_challenge(sid, data):
    print(f"Received join_challenge event with data: {data}")

    challenge_session_id = data.get("challenge_session_id")
    if not challenge_session_id:
        print("no challenge_session_id provided in join_challenge event")  
        return
    
    room = f"challenge:{challenge_session_id}"
    print(f"Joining room {room} for sid {sid}")

    await sio.enter_room(sid, room)
    print(f"{sid} joined {room}")

async def complete_challenge(sid, user_id, challenge_id, challenge_session_id, eval: schemas.EvaluationResponse):
    if not challenge_session_id:
        print("no challenge_session_id provided in complete_challenge event")  
        return
    
    async with SessionLocal() as db:
        print("challenge_session_id : ", challenge_session_id)
        print("challenge_id : ", challenge_id)
        print("user_id : ", user_id)
        print("eval : ", eval)
        print("eval.status : ", eval.status)
        print("eval.reasoning : ", eval.reasoning)

        session_details = schemas.ChallengeCompletion(
            challenge_session_id=challenge_session_id,
            challenge_status=eval.status,
            reason=eval.reasoning,
            user_id=user_id,
            challenge_id=challenge_id
        )

        print("updating challenge session status in DB...")
        try:
            result = await challenge_session.complete_challenge_session(
                db,
                challenge_details=session_details
            )

            print("Challenge session updated in DB with result: ", result)
            print("Emitting challenge_completed event to client with result: ", result.model_dump_json())

            print("Challenge session updated. Sending completion event to client... ")
            await sio.emit(
                "challenge_completed",
                result.model_dump_json(),
                room=f"challenge:{challenge_session_id}"    
            )

            room = f"challenge:{session_details.challenge_session_id}"
            await sio.leave_room(sid, room)

        except Exception as e:
            await db.rollback()
            print(f"Error in complete_challenge event: {e}")
            traceback.print_exc()

@sio.on('complete_challenge')
async def handle_complete_challenge(sid, data):
    """
    Handle challenge completion events emitted directly by the client (e.g. on timeout).
    """
    print(f"Socket.IO: Received complete_challenge event with data: {data}")
    challenge_session_id = data.get("challenge_session_id")
    status = data.get("status")
    reason = data.get("reason", "")
    
    if not challenge_session_id:
        print("no challenge_session_id provided in complete_challenge event")
        return
        
    async with SessionLocal() as db:
        session = await crud.get_challenge_session_by_id(db, challenge_session_id)
        if not session:
            print(f"Challenge session {challenge_session_id} not found in DB")
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
            print(f"Error in send_message: {e}")
            traceback.print_exc()
            raise


async def handle_send_message(payload, db: AsyncSession, sid):
    message_in = schemas.MessageCreate(**payload)

    print(
        f"Received message from user {message_in.sender_id} "
        f"to persona {message_in.receiver_id}: {message_in.text}"
    )

    session_result = await db.execute(
        select(crud.models.ChallengeSession).filter(
            crud.models.ChallengeSession.id == message_in.challenge_session_id
        )
    )
    challenge_session = session_result.scalars().first()

    challenge = None
    if challenge_session:
        if challenge_session.status != 'active':
            print(f"Challenge session {challenge_session.id} is not active (status: {challenge_session.status}). Ignoring message.")
            return

        from app.services import challenge_service
        challenge = await challenge_service.get_challenge_by_id(db, challenge_session.challenge_id)
        if challenge and challenge.estimated_duration_minutes:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            delta = (now - challenge_session.last_resumed_at).total_seconds() if challenge_session.last_resumed_at else 0
            total_elapsed = challenge_session.elapsed_seconds + delta
            if total_elapsed >= challenge.estimated_duration_minutes * 60:
                print(f"Challenge session {challenge_session.id} has timed out. Completing as lost.")
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

    # Save user's message
    raw_message = await crud.create_message(db, message_in)
    message = schemas.MessageResponse.model_validate(raw_message)

    past_messages = []

    if challenge_session:
        past_messages = await message_service.get_message_by_session_id(db, challenge_session.id)

    else:
        # Load DB message history directly
        db_msgs = await crud.get_messages_between_users(
            db,
            message.sender_id,
            message.receiver_id
        )
        past_messages = [
            schemas.MessageResponse.model_validate(m)
            for m in db_msgs
        ]

        # Add latest user message
        past_messages.append(message)

    if challenge_session:
        asyncio.create_task(
            handle_gemini_response(message, past_messages, sid, challenge, challenge_session.id)
        )
    else:
        asyncio.create_task(
            handle_gemini_response(message, past_messages, sid)
        )


async def handle_gemini_response(message : schemas.MessageCreate, past_messages, sid, challenge : Optional[schemas.ChallengeResponse] = None, challenge_session_id=None):
    """
    Background task that uses its own independent database session.
    This avoids using a closed session and prevents connection leaks.
    """

    print("""\n=== Handling Gemini Response in Background Task ===""")

    # Create a new DB session for this background task
    async with SessionLocal() as db:
        try:
            # Get persona info
            persona = await persona_service.get_persona_by_id(db, message.receiver_id)

            # Get user info
            try:
                user_persona = await persona_service.get_persona_by_id(db, message.sender_id)
                user_name = user_persona.name if user_persona else "User"
            except ValueError:
                user_name = "User"

            attempt = None
            if challenge:
                attempt = await challenge_service.get_attempt_number(db, challenge.id, message.sender_id)

            # Generate Gemini response
            gemini_response_in = ask_gemini(
                message.text,
                persona,
                user_name=user_name,
                user_role=user_persona.role if user_persona else None,
                user_bio=user_persona.bio if user_persona else None,
                senderId=message.sender_id,
                past_messages=past_messages,
                challenge=challenge,
                challenge_session_id=challenge_session_id,
                attempt=attempt
            )

            # Save Gemini response
            gemini_message = await crud.create_message(db, gemini_response_in)

            validated_gemini_response = schemas.MessageResponse.model_validate(
                gemini_message
            )

            # Determine message routing: challenge room or user-specific persona chat room
            if message.challenge_session_id:
                room = f"challenge:{message.challenge_session_id}"
            else:
                room = f"user:{validated_gemini_response.receiver_id}"

            # Send response back to the connected client
            await sio.emit(
                "receive_message",
                validated_gemini_response.model_dump_json(),
                room=room
            )

            # Update in-memory history
            past_messages.append(validated_gemini_response)

            if challenge:
                # Check if the session is still active before evaluating
                is_session_active = True
                if challenge_session_id:
                    session_res = await db.execute(select(crud.models.ChallengeSession).filter(crud.models.ChallengeSession.id == challenge_session_id))
                    session = session_res.scalars().first()
                    if session and session.status != 'active':
                        is_session_active = False

                if is_session_active:
                    eval : schemas.EvaluationResponse = evaluate_challenge(
                        challenge,
                        past_messages,
                        persona,
                        user_name=user_name,
                        user_id=message.sender_id
                    )

                    print("""\n=== Challenge Evaluation ===""")
                    print(f"Evaluation result: {eval.status}")
                    print(f"Evaluation reasoning: {eval.reasoning}")

                    if eval.status != ChallengeResult.ACTIVE :
                        # Send response back to the connected client
                        asyncio.create_task(
                            complete_challenge(sid, message.sender_id, challenge.id, challenge_session_id, eval)
                        )
                else:
                    print(f"Session {challenge_session_id} is not active (status: {session.status if session else 'unknown'}). Skipping challenge evaluation.")

            else:
                print(f"Gemini response {gemini_message.text}")

        except Exception as e:
            await db.rollback()
            print(f"Error in handle_gemini_response: {e}")
            traceback.print_exc()
