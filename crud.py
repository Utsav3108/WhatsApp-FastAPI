from sqlalchemy.orm import Session
import models, schemas

def create_message(db: Session, message: schemas.MessageCreate):
    db_message = models.Message(**message.model_dump())
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_messages(db: Session, user_id: int):
    return db.query(models.Message).filter(models.Message.user_id == user_id).all()

def get_message_by_id(db: Session, message_id: int):
    return db.query(models.Message).filter(models.Message.id == message_id).first()

def get_messages_between_users(db: Session, user1_id: int, user2_id: int, limit: int = 50, offset: int = 0):
    return db.query(models.Message).filter(
        ((models.Message.sender_id == user1_id) & (models.Message.receiver_id == user2_id)) |
        ((models.Message.sender_id == user2_id) & (models.Message.receiver_id == user1_id))
    ).order_by(models.Message.timestamp).offset(offset).limit(limit).all()


def search_presidents(db: Session, query: str):
    return db.query(models.President).filter(models.President.name.ilike(f"%{query}%")).all()

def get_president_by_id(db: Session, president_id: int):
    return db.query(models.President).filter(models.President.id == president_id).first()

def get_president_by_name(db: Session, name: str):
    return db.query(models.President).filter(models.President.name == name).first()


def get_all_presidents(db: Session):
    return db.query(models.President).all()


def get_presidents_user_chatted_with(db: Session, user_id: int):
    # Get all unique president IDs that the user has chatted with
    sent_to_presidents = db.query(models.Message.receiver_id).filter(models.Message.sender_id == user_id).distinct()
    received_from_presidents = db.query(models.Message.sender_id).filter(models.Message.receiver_id == user_id).distinct()
    
    president_ids = set([pid for (pid,) in sent_to_presidents] + [pid for (pid,) in received_from_presidents])
    
    # Fetch president details for these IDs
    presidents = db.query(models.President).filter(models.President.id.in_(president_ids)).all()
    
    return presidents

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