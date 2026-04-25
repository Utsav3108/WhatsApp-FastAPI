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


def get_president_by_id(db: Session, president_id: int):
    return db.query(models.President).filter(models.President.id == president_id).first()

def get_all_presidents(db: Session):
    return db.query(models.President).all()

def save_president(db: Session, president: schemas.PresidentCreate):
    if not check_president_exists(db, president.name):
        return create_president(db, president)
    else:        
        db_president = db.query(models.President).filter(models.President.name == president.name).first()
        db_president.desc = president.desc
        db_president.traits = president.traits
        db_president.image_url = president.image_url
        db.commit()
        db.refresh(db_president)
    return db_president

def check_president_exists(db: Session, name: str):
    return db.query(models.President).filter(models.President.name == name).first() is not None

def create_president(db: Session, president: schemas.PresidentCreate):
    
    db_president = models.President(
        name=president.name,
        desc=president.desc,
        traits=president.traits,
        image_url=president.image_url
    )
    db.add(db_president)
    db.commit()
    db.refresh(db_president)
    return db_president