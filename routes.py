from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.s3_service import S3Service
from app import schemas, crud
from app.database import get_db
from app.AppServices.connection_manageer import ConnectionManager

from app.services import message_service, president_service

router = APIRouter()
manager = ConnectionManager()   

s3_service = S3Service()

def get_s3_service():
    return s3_service

@router.get("/search-presidents/{query}", response_model=list[schemas.PresidentResponse])
def search_presidents(query: str, db: Session = Depends(get_db)):
    response = president_service.search_presidents(db, query)
    
    return response

@router.get("/presidents/{user_id}", response_model=list[schemas.PresidentResponse])
def get_presidents_user_chatted_with(user_id: int, db: Session = Depends(get_db)):

    response = president_service.get_presidents_user_chatted_with(db, user_id)

    return response

@router.get("/messages", response_model=list[schemas.MessageResponse])
def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    all_messages = message_service.get_messages_between_users(db, sender_id, receiver_id, limit, offset)

    return all_messages 
