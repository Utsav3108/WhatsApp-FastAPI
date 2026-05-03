from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from typing import List
import schemas, crud, models
from database import SessionLocal
from AppServices.connection_manageer import ConnectionManager
from gemini import ask_gemini

# For Background tasks
import asyncio
import redis

# Import cache functions
import cache

router = APIRouter()
manager = ConnectionManager()

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/presidents")
def read_presidents(db: Session = Depends(get_db)):
    response = crud.get_all_presidents(db)
    PresidentResponseList = [schemas.PresidentResponse.model_validate(p).model_dump() for p in response]
    return PresidentResponseList

@router.post("/messages")
def send_message(message: schemas.MessageCreate, db: Session = Depends(get_db)):
    return crud.create_message(db, message)

@router.get("/messages", response_model=List[schemas.MessageResponse])
def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return crud.get_messages_between_users(
        db, sender_id, receiver_id, limit, offset
    )

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    token = websocket.query_params.get("token")
    if token != "secret":
        await websocket.close(code=1008) # 1008: Policy Violation
        return  
    print("WebSocket connection established for user_id:", user_id)
    await manager.connect(websocket, user_id)
    db = next(get_db())
    try:
        while True:
            payload = await websocket.receive_json()
            await handle_send_message(payload, db)
    except Exception as e:
        print("Error occurred for user_id:", user_id)
        print("Error:", e)
    finally:
        manager.disconnect(user_id)



async def handle_send_message(payload, db: Session):
    """
    handle_send_message is responsible for:
    1. Saving the incoming message to the database.
    2. Asynchronously generating a response from Gemini based on the message and conversation history.
    3. Saving Gemini's response to the database.
    4. Sending Gemini's response back to the user via WebSocket.
    """


    message_in = schemas.MessageCreate(**payload)   
    message = crud.create_message(db, message_in)

    new_message = schemas.MessageResponse.model_validate(message)

    past_messages = []

    cached_response = cache.retrieve_cache(f"conversation_{message.sender_id}_{message.receiver_id}")

    if cached_response:
        past_messages = [schemas.MessageResponse.model_validate(m) for m in cached_response]
        #print("From Redis Cache: ", past_messages[0].text)
    else:
        db_msgs = crud.get_messages_between_users(db, message.sender_id, message.receiver_id)

        past_messages = [schemas.MessageResponse.model_validate(m) for m in db_msgs]

        #print("From Database: ", past_messages[0].text)
        #store_cache(f"conversation_{message.sender_id}_{message.receiver_id}", past_messages)

    past_messages.append(new_message)

    new_cached_response = [m.model_dump() for m in past_messages]

    cache.store_cache(f"conversation_{message.sender_id}_{message.receiver_id}", new_cached_response)

    #print("Message received and stored. Starting background task to get Gemini response...")

    # Background job
    asyncio.create_task(handle_gemini_response(message, past_messages, db))

async def handle_gemini_response(message: models.Message, past_messages: List[schemas.MessageResponse], db: Session):

    president = crud.get_president_by_id(db, message.receiver_id)

    gemini_response = ask_gemini(message.text, president, senderId=message.sender_id, past_messages=past_messages)

    gemini_response = crud.create_message(db, gemini_response)

    validated_gemini_response = schemas.MessageResponse.model_validate(gemini_response)

    response = validated_gemini_response.model_dump_json()

    past_messages.append(validated_gemini_response)

    new_cached_response = [m.model_dump() for m in past_messages]

    cache.store_cache(f"conversation_{message.sender_id}_{message.receiver_id}", new_cached_response)

    await manager.send_to_user(gemini_response.receiver_id, response)


from fastapi import File, UploadFile

@router.post("/upload-image")
async def upload_image_to_s3(file: UploadFile = File(...)):
    from s3_service import S3Service

    s3 = S3Service()

    url = await asyncio.to_thread(s3.upload_file, file.file, file.filename)
    
    return {
        "message": "Image uploaded to S3 successfully.",
        "url": url
    }
