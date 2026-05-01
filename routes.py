from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from typing import List
import schemas, crud, models
from database import SessionLocal
from AppServices.connection_manageer import ConnectionManager
from gemini import ask_gemini
import asyncio

router = APIRouter()
manager = ConnectionManager()

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
    message_in = schemas.MessageCreate(**payload)   
    message = crud.create_message(db, message_in)
    asyncio.create_task(handle_gemini_response(message, db))

async def handle_gemini_response(message: models.Message, db: Session):
    president = crud.get_president_by_id(db, message.receiver_id)
    past_messages = crud.get_messages_between_users(db, message.sender_id, message.receiver_id)
    gemini_response = ask_gemini(message.text, president, senderId=message.sender_id, past_messages=past_messages)
    gemini_response = crud.create_message(db, gemini_response)
    response = schemas.MessageResponse.model_validate(gemini_response).model_dump_json()
    await manager.send_to_user(gemini_response.receiver_id, response)
