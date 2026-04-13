from sqlalchemy.orm import Session
import models, schemas
import datetime

def create_message(db: Session, message: schemas.MessageCreate):
    db_message = models.Message(**message.model_dump())
    print("db_message:", db_message.text)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(models.Message.user_id == user_id).all()

def get_message_by_id(db: Session, message_id: int):
    return db.query(models.Message).filter(models.Message.id == message_id).first()