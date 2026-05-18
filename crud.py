
# --------------------------------------------------------------------------
# Message CRUD
# --------------------------------------------------------------------------

from sqlalchemy.orm import Session
from app import models, schemas

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


# --------------------------------------------------------------------------
# Presidents CRUD
# --------------------------------------------------------------------------

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

# --------------------------------------------------------------------------
# Scenario CRUD
# --------------------------------------------------------------------------

from app.models import Scenario, ScenarioContext
from app.schemas import ScenarioCreate, ScenarioContextCreate
from sqlalchemy.exc import IntegrityError

def get_all_scenarios(db: Session):
    return db.query(Scenario).all()

def get_scenario_by_id(db: Session, scenario_id: str):
    return db.query(Scenario).filter(Scenario.id == scenario_id).first()

def get_scenario_context_by_scenario_id(db: Session, scenario_id: str):
    return db.query(ScenarioContext).filter(ScenarioContext.scenario_id == scenario_id).first()

def upsert_scenario(db: Session, scenario: ScenarioCreate):
    db_scenario = get_scenario_by_id(db, scenario.id)
    context_data = scenario.context.model_dump()
    if db_scenario:
        updated = False
        if db_scenario.title != scenario.title:
            db_scenario.title = scenario.title
            updated = True
        if db_scenario.image_url != scenario.image_url:
            db_scenario.image_url = scenario.image_url
            updated = True
        db_context = get_scenario_context_by_scenario_id(db, scenario.id)
        if db_context:
            for field in ["setting", "goal", "stakes", "platform"]:
                if getattr(db_context, field) != context_data[field]:
                    setattr(db_context, field, context_data[field])
                    updated = True
        else:
            db_context = ScenarioContext(scenario_id=scenario.id, **context_data)
            db.add(db_context)
            updated = True
        if updated:
            db.commit()
            db.refresh(db_scenario)
        return db_scenario
    else:
        db_scenario = Scenario(
            id=scenario.id,
            title=scenario.title,
            image_url=scenario.image_url
        )
        db.add(db_scenario)
        db.commit()
        db.refresh(db_scenario)
        db_context = ScenarioContext(scenario_id=scenario.id, **context_data)
        db.add(db_context)
        db.commit()
        db.refresh(db_context)
        return db_scenario
