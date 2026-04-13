from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from fastapi import WebSocket
from AppServices.connection_manageer import ConnectionManager


from gemini import ask_gemini
import models, schemas, crud
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

api = FastAPI()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
            print(f"Received: {data}")

            message = schemas.MessageCreate(**data)
            message = crud.create_message(db, message)

            gemini_response = ask_gemini(message.text)

            print("Gemini response:", gemini_response)

            gemini_response = schemas.MessageCreate(**gemini_response)
            gemini_response = crud.create_message(db, gemini_response)

            message_to_send = crud.get_message_by_id(db, gemini_response.id)


            response = schemas.MessageResponse.model_validate(message_to_send).model_dump_json()

            print("response to send:", response)

            await manager.send_to_user(message_to_send.sender_id, response)

    except:
        manager.disconnect(user_id)