
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
# personas CRUD
# --------------------------------------------------------------------------

def search_personas(db: Session, query: str):
    return db.query(models.Persona).filter(models.Persona.name.ilike(f"%{query}%")).all()

def get_persona_by_id(db: Session, persona_id: int):
    return db.query(models.Persona).filter(models.Persona.id == persona_id).first()

def get_persona_by_name(db: Session, name: str):
    return db.query(models.Persona).filter(models.Persona.name == name).first()

def get_all_personas(db: Session, limit: int = 50, offset: int = 0):
    return db.query(models.Persona).offset(offset).limit(limit).all()

def get_personas_user_chatted_with(db: Session, user_id: int):
    # Get all unique persona IDs that the user has chatted with
    sent_to_personas = db.query(models.Message.receiver_id).filter(models.Message.sender_id == user_id).distinct()
    received_from_personas = db.query(models.Message.sender_id).filter(models.Message.receiver_id == user_id).distinct()
    persona_ids = set([pid for (pid,) in sent_to_personas] + [pid for (pid,) in received_from_personas])
    # Fetch persona details for these IDs
    personas = db.query(models.Persona).filter(models.Persona.id.in_(persona_ids)).all()
    return personas

def save_persona(db: Session, persona: schemas.personaCreate):
    if not check_persona_exists(db, persona.name):
        return create_persona(db, persona)
    else:        
        db_persona = db.query(models.Persona).filter(models.Persona.name == persona.name).first()
        db_persona.desc = persona.desc
        db_persona.traits = persona.traits
        db_persona.image_url = persona.image_url
        db.commit()
        db.refresh(db_persona)
    return db_persona

def check_persona_exists(db: Session, name: str):
    return db.query(models.Persona).filter(models.Persona.name == name).first() is not None

def create_persona(db: Session, persona: schemas.personaCreate):
    db_persona = models.Persona(
        name=persona.name,
        desc=persona.desc,
        traits=persona.traits,
        image_url=persona.image_url
    )
    db.add(db_persona)
    db.commit()
    db.refresh(db_persona)
    return db_persona

# --------------------------------------------------------------------------
# Challenge CRUD
# --------------------------------------------------------------------------

from app.models import Challenge, ChallengeContext
from app.schemas import ChallengeCreate, ChallengeContextCreate
from sqlalchemy.exc import IntegrityError


def get_all_challenges(db: Session):
    return db.query(Challenge).all()


def get_challenge_by_id(db: Session, challenge_id: str):
    return db.query(Challenge).filter(Challenge.id == challenge_id).first()

def get_challenge_context_by_challenge_id(db: Session, challenge_id: str):
    return db.query(ChallengeContext).filter(ChallengeContext.challenge_id == challenge_id).first()
def _update_model_fields(model_instance, source, fields):
    """
    Update model fields from a source object (Pydantic model) or dict.

    Returns:
        bool: True if at least one field was changed.
    """
    updated = False

    for field in fields:
        if isinstance(source, dict):
            new_value = source.get(field)
        else:
            new_value = getattr(source, field, None)

        if getattr(model_instance, field) != new_value:
            setattr(model_instance, field, new_value)
            updated = True

    return updated



def _create_challenge_model(challenge: ChallengeCreate) -> Challenge:
    """
    Create a Challenge ORM instance from the Pydantic model.
    """
    return Challenge(
        id=challenge.id,
        image_url=challenge.image_url,
        title=challenge.title,
        subtitle=challenge.subtitle,
        description=challenge.description,
        short_description=challenge.short_description,
        categories=challenge.categories,
        suggested_personas=challenge.suggested_personas,
        difficulty=challenge.difficulty,
        difficulty_settings=challenge.difficulty_settings,
        estimated_duration_minutes=challenge.estimated_duration_minutes,
        challenge_rules=challenge.challenge_rules,
        selected_persona_id=challenge.selected_persona_id
    )


def update_challenge(
    db: Session,
    challenge: Challenge
):
    merged_challenge = db.merge(challenge)

    db.commit()

    db.refresh(merged_challenge)

    return merged_challenge

def upsert_challenges(db: Session, challenge: ChallengeCreate):
    """
    Create or update a challenge and its associated context.

    Behavior:
    - If the challenge exists, only modified fields are updated.
    - If the challenge does not exist, it is created.
    - ChallengeContext is created, updated, or left absent if no context is provided.
    - Only one commit is performed for the entire operation.
    """

    # Convert optional nested Pydantic model into a dictionary
    context_data = challenge.context.model_dump() if challenge.context else None

    # Fields stored directly in Challenge table
    challenge_fields = [
        "image_url",
        "title",
        "subtitle",
        "description",
        "short_description",
        "categories",
        "suggested_personas",
        "selected_persona_id",
        "difficulty",
        "difficulty_settings",
        "estimated_duration_minutes",
        "challenge_rules",
    ]

    # Fields stored in ChallengeContext table
    context_fields = [
        "setting",
        "environment",
        "goal",
        "stakes",
        "platform",
    ]

    # Look up existing challenge
    db_challenge = get_challenge_by_id(db, challenge.id)

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    if db_challenge is None:
        # Create challenge
        db_challenge = _create_challenge_model(challenge)
        db.add(db_challenge)

        # Flush so the challenge exists before creating related context
        db.flush()

        # Create context if provided
        if context_data:
            db_context = ChallengeContext(
                challenge_id=db_challenge.id,
                **context_data,
            )
            db.add(db_context)

        db.commit()
        db.refresh(db_challenge)
        return db_challenge

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------
    updated = False

    # Update Challenge fields
    updated |= _update_model_fields(
        model_instance=db_challenge,
        source=challenge,
        fields=challenge_fields,
    )

    # Update/Create ChallengeContext if context is provided
    if context_data:
        db_context = get_challenge_context_by_challenge_id(db, challenge.id)

        if db_context is None:
            db_context = ChallengeContext(
                challenge_id=db_challenge.id,
                **context_data,
            )
            db.add(db_context)
            updated = True
        else:
            updated |= _update_model_fields(
                model_instance=db_context,
                source=context_data,
                fields=context_fields,
            )

    # Commit only if something changed
    if updated:
        db.commit()
        db.refresh(db_challenge)

    return db_challenge



# ChallengeSession CRUD
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import ChallengeSession

def get_active_session(
    db: Session,
    user_id: int,
    challenge_id: str
):

    return db.query(ChallengeSession).filter(
        ChallengeSession.user_id == user_id,
        ChallengeSession.challenge_id == challenge_id,
        ChallengeSession.status == "active"
    ).first()


def create_challenge_session(
    db: Session,
    user_id: int,
    challenge_id: str,
    persona_id: int,
    storyline: str
):

    session = ChallengeSession(
        user_id=user_id,
        challenge_id=challenge_id,
        persona_id=persona_id,
        storyline=storyline
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def complete_session(
    db: Session,
    session: ChallengeSession,
    status: str,
    reason: str
):

    session.status = status
    session.result_reason = reason
    session.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(session)

    return session