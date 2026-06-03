from typing import Optional

from fastapi import Depends
import socketio
import asyncio
from sqlalchemy.orm import Session

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

async def complete_challenge(sid, user_id, challenge_id, challenge_session_id, eval: schemas.EvaluationResponse):

    if not challenge_session_id:
        print("no challenge_session_id provided in complete_challenge event")  
        return
    
    db = SessionLocal()


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
        result = challenge_session.complete_challenge_session(
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
        db.rollback()
        print(f"Error in complete_challenge event: {e}")
        raise

    finally:
        db.close()

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

        # user_id : int = payload.get('sender_id')
        # challenge_id : str = payload.get('challenge_id')
        # challenge_session_id : int = payload.get('challenge_session_id')

        # challenge_session = db.query(
        #             crud.models.ChallengeSession
        #             ).filter(
        #             crud.models.ChallengeSession.id
        #             == challenge_session_id
        #         ).first()

        # asyncio.create_task(
        #     complete_challenge(
        #         sid=sid,
        #         user_id=user_id,
        #         challenge_id=challenge_session.challenge_id if challenge_session else None,
        #         challenge_session_id=challenge_session_id,
        #         eval=schemas.EvaluationResponse(
        #             status=enums.ChallengeResult.WON_OBJECTIVE_COMPLETED,
        #             reasoning="Challenge time expired"
        #         )
        #     )
        # )

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

    # Save user's message
    raw_message = crud.create_message(db, message_in)
    message = schemas.MessageResponse.model_validate(raw_message)

    challenge = None
    past_messages = []

    if challenge_session:

        from app.services import challenge_service
        past_messages = message_service.get_message_by_session_id(db, challenge_session.id)
        challenge = challenge_service.get_challenge_by_id(db, challenge_session.challenge_id)

    else:
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
        past_messages.append(message)

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
    db = SessionLocal()

    try:

        # Get persona info
        persona = persona_service.get_persona_by_id(db, message.receiver_id)

        attempt = None
        if challenge:
            attempt = challenge_service.get_attempt_number(db, challenge.id, message.sender_id)

        # Generate Gemini response
        gemini_response_in = ask_gemini(
            message.text,
            persona,
            senderId=message.sender_id,
            past_messages=past_messages,
            challenge=challenge,
            challenge_session_id=challenge_session_id,
            attempt=attempt
        )

        # Save Gemini response
        gemini_message = crud.create_message(db, gemini_response_in)

        validated_gemini_response = schemas.MessageResponse.model_validate(
            gemini_message
        )

        # Send response back to the connected client
        await sio.emit(
            "receive_message",
            validated_gemini_response.model_dump_json(),
            room=f"challenge:{message.challenge_session_id}"
        )

        # Update in-memory history
        past_messages.append(validated_gemini_response)

        if challenge:
            
            eval : schemas.EvaluationResponse = evaluate_challenge(
                challenge,
                past_messages,
                persona,
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



    except Exception as e:
        db.rollback()
        print(f"Error in handle_gemini_response: {e}")

    finally:
        # Always release the connection back to the pool
        db.close()

