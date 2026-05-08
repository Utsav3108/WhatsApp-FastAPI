import socketio
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.AppServices.connection_manageer import ConnectionManager
import app.schemas as schemas
import app.crud as crud
import app.cache as cache
from app.gemini import ask_gemini
import asyncio
from app.database import get_db
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
sio_app = socketio.ASGIApp(sio)
manager = ConnectionManager()

# Helper to get DB session

# Socket.IO event for connection
data_user_map = {}

@sio.event
def connect(sid, environ):
    print(f"Socket.IO: {sid} connected")

@sio.event
def disconnect(sid):
    print(f"Socket.IO: {sid} disconnected")
    # Optionally handle user disconnect logic

@sio.event
async def join(sid, data):
    user_id = data.get('user_id')
    if user_id:
        data_user_map[sid] = user_id
        await sio.save_session(sid, {'user_id': user_id})
        print(f"User {user_id} joined with sid {sid}")

@sio.event
async def send_message(sid, payload):
    db = next(get_db())
    await handle_send_message(payload, db, sid)

async def handle_send_message(payload, db: Session, sid):
    message_in = schemas.MessageCreate(**payload)

    print(f"Received message from user {message_in.sender_id} to president {message_in.receiver_id}: {message_in.text}")

    message = crud.create_message(db, message_in)
    new_message = schemas.MessageResponse.model_validate(message)
    past_messages = []
    key = cache.create_cache_message_key(message.sender_id, message.receiver_id)
    cached_response = cache.retrieve_cache(key)
    if cached_response:
        past_messages = [schemas.MessageResponse.model_validate(m) for m in cached_response]
    else:
        db_msgs = crud.get_messages_between_users(db, message.sender_id, message.receiver_id)
        past_messages = [schemas.MessageResponse.model_validate(m) for m in db_msgs]
    past_messages.append(new_message)
    new_cached_response = [m.model_dump() for m in past_messages]
    cache.store_cache(key, new_cached_response)
    asyncio.create_task(handle_gemini_response(message, past_messages, db, sid))

async def handle_gemini_response(message, past_messages, db, sid):
    president = crud.get_president_by_id(db, message.receiver_id)
    gemini_response = ask_gemini(message.text, president, senderId=message.sender_id, past_messages=past_messages)
    gemini_response = crud.create_message(db, gemini_response)
    validated_gemini_response = schemas.MessageResponse.model_validate(gemini_response)
    response = validated_gemini_response.model_dump_json()
    past_messages.append(validated_gemini_response)
    new_cached_response = [m.model_dump() for m in past_messages]
    key = cache.create_cache_message_key(message.sender_id, message.receiver_id)
    cache.store_cache(key, new_cached_response)
    # Send Gemini's response back to the user
    await sio.emit('receive_message', response, room=sid)
