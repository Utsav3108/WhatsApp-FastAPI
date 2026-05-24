from fastapi import Depends
import socketio
import asyncio
from sqlalchemy.orm import Session

from app.AppServices.connection_manageer import ConnectionManager
import app.schemas as schemas
import app.crud as crud
import app.cache as cache
from app.gemini import ask_gemini
from app.database import SessionLocal, get_db

# Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
sio_app = socketio.ASGIApp(sio)
manager = ConnectionManager()

# Maps socket session ID -> user ID
data_user_map = {}


# --------------------------------------------------------------------------
# Connection Events
# --------------------------------------------------------------------------

@sio.event
def connect(sid, environ):
    print(f"Socket.IO: {sid} connected")


@sio.event
def disconnect(sid):
    print(f"Socket.IO: {sid} disconnected")
    data_user_map.pop(sid, None)

@sio.event
async def join(sid, data):
    user_id = data.get("user_id")
    if user_id is not None:
        data_user_map[sid] = user_id
        await sio.save_session(sid, {"user_id": user_id})
        # print(f"User {user_id} joined with sid {sid}")


@sio.event
async def join_challenge(sid, data):

    print(f"Received join_challenge event with data: {data}")

    challenge_session_id = data.get(
        "challenge_session_id"
    )

    if not challenge_session_id:
        print("no challenge_session_id provided in join_challenge event")  
        return
    
    room = f"challenge:{challenge_session_id}"

    print(f"Joining room {room} for sid {sid}")

    await sio.enter_room(sid, room)

    print(f"{sid} joined {room}")


# --------------------------------------------------------------------------
# Message Events
# --------------------------------------------------------------------------

@sio.event
async def send_message(sid, payload):
    """
    Create a new database session for this Socket.IO event and ensure it is
    always closed, even if an exception occurs.
    """
    db = SessionLocal()

    try:
        await handle_send_message(payload, db, sid)

    except Exception as e:
        db.rollback()
        print(f"Error in send_message: {e}")
        raise

    finally:
        # This is the critical fix that returns the connection to SQLAlchemy's pool.
        db.close()


async def handle_send_message(payload, db: Session, sid):

    message_in = schemas.MessageCreate(**payload)

    print(
        f"Received message from user {message_in.sender_id} "
        f"to persona {message_in.receiver_id}: {message_in.text}"
    )

    challenge_session = db.query(
    crud.models.ChallengeSession
    ).filter(
    crud.models.ChallengeSession.id
    == message_in.challenge_session_id
    ).first()

    if not challenge_session:
        # print(f"Challenge session {message_in.challenge_session_id} not found.")
        return

    # Save user's message
    message = crud.create_message(db, message_in)
    new_message = schemas.MessageResponse.model_validate(message)

    # print(f"Saved user message with ID {message.id} to DB")

    # Load cached or DB message history
    key = cache.create_cache_message_key(
        message.sender_id,
        message.receiver_id
    )

    cached_response = cache.retrieve_cache(key)

    if cached_response:
        past_messages = [
            schemas.MessageResponse.model_validate(m)
            for m in cached_response
        ]
    else:
        db_msgs = crud.get_messages_between_users(
            db,
            message.sender_id,
            message.receiver_id
        )
        past_messages = [
            schemas.MessageResponse.model_validate(m)
            for m in db_msgs
        ]

    # print(f"Loaded {len(past_messages)} past messages between user {message.sender_id} and persona {message.receiver_id}")

    # Add latest user message
    past_messages.append(new_message)

    # Update cache for messages
    cache.store_cache(
        key,
        [m.model_dump() for m in past_messages]
    )

    # --- Update personas chatted cache if needed ---
    personas_chat_key = cache.create_personas_chat_key(message.sender_id)
    personas_chatted = cache.retrieve_cache(personas_chat_key)
    if personas_chatted is not None:
        if not any(p.get('id') == message.receiver_id for p in personas_chatted):
            persona = db.query(crud.models.Persona).filter_by(id=message.receiver_id).first()
            if persona:
                from app.schemas import PersonaResponse
                persona_data = PersonaResponse.model_validate(persona).model_dump()
                personas_chatted.append(persona_data)
                cache.store_cache(personas_chat_key, personas_chatted)

    # Pass scenario_id if present

    # print(f"Message is part of challenge session {message_in.challenge_session_id}")

    challenge = None

    if challenge_session:
        from app.services import challenge_service
        challenge = challenge_service.get_challenge_by_id(db, challenge_session.challenge_id)

        # print(f"Challenge session {challenge_session.id} is associated with challenge {challenge.id if challenge else 'N/A'}")

    # print(f"Challenge session {challenge_session.id} is associated with challenge {challenge.id if challenge else 'N/A'}")

    from datetime import datetime

    if datetime.utcnow() >= challenge_session.expires_at:

        challenge_session.status = "lost_timeout"

        db.commit()

        await sio.emit(
            "challenge_completed",
            {
                "status": "lost_timeout",
                "message": "Time is up."
            },
            room=f"challenge:{challenge_session.id}"
        )

        # print(f"Challenge session {challenge_session.id} has expired. Marked as lost_timeout.")
        return
    

    # print(f"Scheduling background task to handle Gemini response for message {message.id} in challenge session {challenge_session.id}")
    # IMPORTANT:
    # Do not pass the current `db` session to a background task because it
    # will be closed when this event handler finishes.
    #
    # Instead, create a fresh DB session inside the background task.
    asyncio.create_task(
        handle_gemini_response(message, past_messages, sid, challenge)
    )


async def handle_gemini_response(message, past_messages, sid, challenge=None):
    """
    Background task that uses its own independent database session.
    This avoids using a closed session and prevents connection leaks.
    """

    print("""\n=== Handling Gemini Response in Background Task ===""")

    # Create a new DB session for this background task
    db = SessionLocal()

    try:

        # Get persona info
        persona = crud.get_persona_by_id(db, message.receiver_id)

        # Generate Gemini response
        gemini_response_in = ask_gemini(
            message.text,
            persona,
            senderId=message.sender_id,
            past_messages=past_messages,
            challenge=challenge
        )

        # Save Gemini response
        gemini_message = crud.create_message(db, gemini_response_in)

        validated_gemini_response = schemas.MessageResponse.model_validate(
            gemini_message
        )

        # Update in-memory history
        past_messages.append(validated_gemini_response)

        print(f"Gemini response {gemini_message.text}")

        # Update cache
        key = cache.create_cache_message_key(
            message.sender_id,
            message.receiver_id
        )

        cache.store_cache(
            key,
            [m.model_dump() for m in past_messages]
        )

        # Send response back to the connected client
        await sio.emit(
            "receive_message",
            validated_gemini_response.model_dump_json(),
            room=f"challenge:{message.challenge_session_id}"
        )

    except Exception as e:
        db.rollback()
        print(f"Error in handle_gemini_response: {e}")

    finally:
        # Always release the connection back to the pool
        db.close()

