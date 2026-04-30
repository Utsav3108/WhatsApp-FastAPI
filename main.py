from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from fastapi import WebSocket
from AppServices.connection_manageer import ConnectionManager


from gemini import ask_gemini
import models, schemas, crud
from database import engine, SessionLocal

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

file_path = os.path.join(BASE_DIR, "data.json")

with open(file_path, "r") as f:
    data = json.load(f)

print(data)

models.Base.metadata.create_all(bind=engine)

api = FastAPI()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_president():
    for president in data:
        president_in = schemas.PresidentCreate(
            name=president["name"],
            desc=president["desc"],
            traits=president["traits"],
            image_url=president["image_url"]
        )
        with SessionLocal() as db:
            crud.save_president(db, president_in)

@api.on_event("startup")
def startup_event():
    save_president()


@api.get("/presidents")
def read_presidents(db: Session = Depends(get_db)):

    response = crud.get_all_presidents(db)

    PresidentResponseList = [schemas.PresidentResponse.model_validate(p).model_dump() for p in response]

    return PresidentResponseList

@api.post("/messages")
def send_message(message: schemas.MessageCreate, db: Session = Depends(get_db)):

    return crud.create_message(db, message)


@api.get("/messages/{user_id}")
def read_messages(user_id: int, db: Session = Depends(get_db)):
    return crud.get_messages(db, user_id)



manager = ConnectionManager()

@api.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, db: Session = Depends(get_db)):

    token = websocket.query_params.get("token")

    if token != "secret":
        await websocket.close(code=1008) # 1008: Policy Violation
        return  

    print("WebSocket connection established for user_id:", user_id)
    await manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_json()

            message = schemas.MessageCreate(**data)
            message = crud.create_message(db, message)

            president = crud.get_president_by_id(db, message.receiver_id)

            past_messages = crud.get_messages_between_users(db, message.sender_id, message.receiver_id)

            gemini_response = ask_gemini(message.text, president, senderId=message.sender_id, past_messages=past_messages)

            gemini_response = crud.create_message(db, gemini_response)

            message_to_send = crud.get_message_by_id(db, gemini_response.id)

            response = schemas.MessageResponse.model_validate(message_to_send).model_dump_json()

            await manager.send_to_user(message_to_send.receiver_id, response)

    except:
        manager.disconnect(user_id)