import socketio
import asyncio
from sqlalchemy.orm import Session

from app.AppServices.connection_manageer import ConnectionManager
import app.schemas as schemas
import app.crud as crud
import app.cache as cache
from app.gemini import ask_gemini
from app.database import SessionLocal

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
        print(f"User {user_id} joined with sid {sid}")


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
        f"to president {message_in.receiver_id}: {message_in.text}"
    )

    # Save user's message
    message = crud.create_message(db, message_in)
    new_message = schemas.MessageResponse.model_validate(message)

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


    # Add latest user message
    past_messages.append(new_message)

    # Update cache for messages
    cache.store_cache(
        key,
        [m.model_dump() for m in past_messages]
    )

    # --- Update presidents chatted cache if needed ---
    # This cache stores the list of presidents a user has chatted with
    presidents_chat_key = cache.create_presidents_chat_key(message.sender_id)
    presidents_chatted = cache.retrieve_cache(presidents_chat_key)
    if presidents_chatted is not None:
        # Check if the receiver_id (president) is already in the cache
        if not any(p.get('id') == message.receiver_id for p in presidents_chatted):
            # Fetch the president info from DB
            president = db.query(crud.models.President).filter_by(id=message.receiver_id).first()
            if president:
                from app.schemas import PresidentResponse
                president_data = PresidentResponse.model_validate(president).model_dump()
                presidents_chatted.append(president_data)
                cache.store_cache(presidents_chat_key, presidents_chatted)
    # If not in cache, the next API call will repopulate it as usual

    # IMPORTANT:
    # Do not pass the current `db` session to a background task because it
    # will be closed when this event handler finishes.
    #
    # Instead, create a fresh DB session inside the background task.
    asyncio.create_task(
        handle_gemini_response(message, past_messages, sid)
    )


async def handle_gemini_response(message, past_messages, sid):
    """
    Background task that uses its own independent database session.
    This avoids using a closed session and prevents connection leaks.
    """
    db = SessionLocal()

    try:
        # Get president info
        president = crud.get_president_by_id(db, message.receiver_id)

        # Generate Gemini response
        gemini_response_in = ask_gemini(
            message.text,
            president,
            senderId=message.sender_id,
            past_messages=past_messages
        )

        # Save Gemini response
        gemini_message = crud.create_message(db, gemini_response_in)

        validated_gemini_response = schemas.MessageResponse.model_validate(
            gemini_message
        )

        # Update in-memory history
        past_messages.append(validated_gemini_response)

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
            room=sid
        )

    except Exception as e:
        db.rollback()
        print(f"Error in handle_gemini_response: {e}")

    finally:
        # Always release the connection back to the pool
        db.close()