from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app import models, schemas
from app.models import Challenge, ChallengeAttempt, ChallengeContext, ChallengeSession, Persona, Message

# --------------------------------------------------------------------------
# Message CRUD
# --------------------------------------------------------------------------

async def create_message(db: AsyncSession, message: schemas.MessageCreate):
    db_message = models.Message(**message.model_dump())
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message

async def get_messages(db: AsyncSession, user_id: int):
    result = await db.execute(select(models.Message).filter(models.Message.user_id == user_id))
    return result.scalars().all()

async def get_message_by_id(db: AsyncSession, message_id: int):
    result = await db.execute(select(models.Message).filter(models.Message.id == message_id))
    return result.scalars().first()

async def get_messages_between_users(db: AsyncSession, user1_id: int, user2_id: int, limit: int = 50, offset: int = 0):
    result = await db.execute(
        select(models.Message).filter(
            (
                ((models.Message.sender_id == user1_id) & (models.Message.receiver_id == user2_id)) |
                ((models.Message.sender_id == user2_id) & (models.Message.receiver_id == user1_id))
            ) &
            (models.Message.challenge_session_id == None)  # Exclude messages that are part of a challenge session
        ).order_by(models.Message.timestamp).offset(offset).limit(limit)
    )
    return result.scalars().all()

async def get_messages_by_challenge_session_id(db: AsyncSession, challenge_session_id: int):
    result = await db.execute(
        select(models.Message).filter(
            models.Message.challenge_session_id == challenge_session_id
        ).order_by(models.Message.timestamp)
    )
    return result.scalars().all()

# --------------------------------------------------------------------------
# personas CRUD
# --------------------------------------------------------------------------

async def search_personas(db: AsyncSession, query: str):
    result = await db.execute(
        select(models.Persona).filter(models.Persona.name.ilike(f"%{query}%"))
    )
    return result.scalars().all()

async def get_persona_by_id(db: AsyncSession, persona_id: int):
    result = await db.execute(
        select(models.Persona).filter(models.Persona.id == persona_id)
    )
    return result.scalars().first()

async def get_persona_by_name(db: AsyncSession, name: str):
    result = await db.execute(
        select(models.Persona).filter(models.Persona.name == name)
    )
    return result.scalars().first()

async def get_all_personas(db: AsyncSession, limit: int = 50, offset: int = 0):
    result = await db.execute(
        select(models.Persona).offset(offset).limit(limit)
    )
    return result.scalars().all()

async def get_personas_user_chatted_with(db: AsyncSession, user_id: int):
    # Get all unique persona IDs that the user has chatted with
    sent_res = await db.execute(select(models.Message.receiver_id).filter(models.Message.sender_id == user_id).distinct())
    received_res = await db.execute(select(models.Message.sender_id).filter(models.Message.receiver_id == user_id).distinct())
    
    sent_to_personas = [row[0] for row in sent_res.all()]
    received_from_personas = [row[0] for row in received_res.all()]
    persona_ids = list(set(sent_to_personas + received_from_personas))
    
    if not persona_ids:
        return []
        
    result = await db.execute(select(models.Persona).filter(models.Persona.id.in_(persona_ids)))
    return result.scalars().all()

async def save_persona(db: AsyncSession, persona: schemas.PersonaCreate):
    exists = await check_persona_exists(db, persona.name)
    if not exists:
        return await create_persona(db, persona)
    else:        
        result = await db.execute(select(models.Persona).filter(models.Persona.name == persona.name))
        db_persona = result.scalars().first()
        db_persona.desc = persona.desc
        db_persona.traits = persona.traits
        db_persona.image_url = persona.image_url
        await db.commit()
        await db.refresh(db_persona)
    return db_persona

async def check_persona_exists(db: AsyncSession, name: str):
    result = await db.execute(select(models.Persona).filter(models.Persona.name == name))
    return result.scalars().first() is not None

async def create_persona(db: AsyncSession, persona: schemas.PersonaCreate):
    db_persona = models.Persona(
        name=persona.name,
        desc=persona.desc,
        traits=persona.traits,
        image_url=persona.image_url
    )
    db.add(db_persona)
    await db.commit()
    await db.refresh(db_persona)
    return db_persona

# --------------------------------------------------------------------------
# Challenge CRUD
# --------------------------------------------------------------------------

async def get_all_challenges(db: AsyncSession):
    result = await db.execute(
        select(Challenge).options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        )
    )
    return result.scalars().all()

async def get_challenge_by_id(db: AsyncSession, challenge_id: str):
    result = await db.execute(
        select(Challenge).options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        ).filter(Challenge.id == challenge_id)
    )
    return result.scalars().first()

async def get_challenge_context_by_challenge_id(db: AsyncSession, challenge_id: str):
    result = await db.execute(
        select(ChallengeContext).filter(ChallengeContext.challenge_id == challenge_id)
    )
    return result.scalars().first()

def _update_model_fields(model_instance, source, fields):
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

def _create_challenge_model(challenge: schemas.ChallengeCreate) -> Challenge:
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

async def update_challenge(db: AsyncSession, challenge: Challenge):
    merged_challenge = await db.merge(challenge)
    await db.commit()
    return await get_challenge_by_id(db, merged_challenge.id)

async def upsert_challenges(db: AsyncSession, challenge: schemas.ChallengeCreate):
    context_data = challenge.context.model_dump() if challenge.context else None

    challenge_fields = [
        "image_url", "title", "subtitle", "description", "short_description",
        "categories", "suggested_personas", "selected_persona_id", "difficulty",
        "difficulty_settings", "estimated_duration_minutes", "challenge_rules"
    ]

    context_fields = ["setting", "environment", "goal", "stakes", "platform"]

    db_challenge = await get_challenge_by_id(db, challenge.id)

    # CREATE
    if db_challenge is None:
        db_challenge = _create_challenge_model(challenge)
        db.add(db_challenge)
        await db.flush()

        if context_data:
            db_context = ChallengeContext(
                challenge_id=db_challenge.id,
                **context_data,
            )
            db.add(db_context)

        await db.commit()
        return await get_challenge_by_id(db, db_challenge.id)

    # UPDATE
    updated = False
    updated |= _update_model_fields(
        model_instance=db_challenge,
        source=challenge,
        fields=challenge_fields,
    )

    if context_data:
        db_context = await get_challenge_context_by_challenge_id(db, challenge.id)

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

    if updated:
        await db.commit()

    return await get_challenge_by_id(db, db_challenge.id)

# --------------------------------------------------------------------------
# ChallengeSession CRUD
# --------------------------------------------------------------------------

async def get_challenge_session_by_id(db: AsyncSession, session_id: int):
    result = await db.execute(
        select(ChallengeSession).filter(ChallengeSession.id == session_id)
    )
    return result.scalars().first()

async def get_existing_session(db: AsyncSession, user_id: int, challenge_id: str):
    result = await db.execute(
        select(ChallengeSession).filter(
            ChallengeSession.user_id == user_id,
            ChallengeSession.challenge_id == challenge_id,
            ChallengeSession.status == 'active'
        )
    )
    return result.scalars().first()

async def create_challenge_session(db: AsyncSession, user_id: int, challenge_id: str, persona_id: int, intro: schemas.StorylineResponse):
    session = ChallengeSession(
        user_id=user_id,
        challenge_id=challenge_id,
        persona_id=persona_id,
        storyline=intro.storyline,
        call_to_action=intro.call_to_action
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def complete_session(db: AsyncSession, session: ChallengeSession, status: str, reason: str):
    session.status = status
    session.result_reason = reason
    session.completed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session

async def get_attempts(db: AsyncSession, user_id: int, challenge_id: str):
    result = await db.execute(
        select(models.ChallengeAttempt).filter(
            models.ChallengeAttempt.user_id == user_id,
            models.ChallengeAttempt.challenge_id == challenge_id
        )
    )
    return result.scalars().all()