from datetime import datetime, timedelta
import hashlib
from sqlalchemy import select, and_, or_, func, desc
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

async def search_personas(db: AsyncSession, query: str, limit: int = 50, offset: int = 0):
    result = await db.execute(
        select(models.Persona)
        .filter(models.Persona.name.ilike(f"%{query}%"))
        .limit(limit)
        .offset(offset)
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

async def get_personas_user_chatted_with(db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0):
    # Get all unique persona IDs that the user has chatted with in a personalized way (no challenge session)
    sent_res = await db.execute(
        select(models.Message.receiver_id)
        .filter(models.Message.sender_id == user_id, models.Message.challenge_session_id == None)
        .distinct()
    )
    received_res = await db.execute(
        select(models.Message.sender_id)
        .filter(models.Message.receiver_id == user_id, models.Message.challenge_session_id == None)
        .distinct()
    )
    
    sent_to_personas = [row[0] for row in sent_res.all()]
    received_from_personas = [row[0] for row in received_res.all()]
    persona_ids = list(set(sent_to_personas + received_from_personas))
    
    if not persona_ids:
        return []
        
    result = await db.execute(
        select(models.Persona)
        .filter(models.Persona.id.in_(persona_ids))
        .limit(limit)
        .offset(offset)
    )
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
        db_persona.is_human = persona.is_human
        db_persona.category = persona.category
        db_persona.email = persona.email
        db_persona.role = persona.role
        db_persona.bio = persona.bio
        db_persona.settings = persona.settings
        db.add(db_persona)
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
        image_url=persona.image_url,
        is_human=persona.is_human,
        category=persona.category,
        email=persona.email,
        role=persona.role,
        bio=persona.bio,
        settings=persona.settings
    )
    db.add(db_persona)
    await db.commit()
    await db.refresh(db_persona)
    return db_persona

async def update_user_profile(db: AsyncSession, user_id: int, profile_in: schemas.UserProfileUpdate):
    result = await db.execute(select(models.Persona).filter(models.Persona.id == user_id))
    db_persona = result.scalars().first()
    if db_persona:
        if profile_in.role is not None:
            db_persona.role = profile_in.role
        if profile_in.bio is not None:
            db_persona.bio = profile_in.bio
        if profile_in.settings is not None:
            db_persona.settings = profile_in.settings
        db.add(db_persona)
        await db.commit()
        await db.refresh(db_persona)
    return db_persona

# --------------------------------------------------------------------------
# Challenge CRUD
# --------------------------------------------------------------------------

async def get_all_challenges(db: AsyncSession, q: str | None = None, limit: int = 50, offset: int = 0):
    stmt = (
        select(Challenge).options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        )
        .filter(Challenge.for_user == True)
    )
    if q:
        q_filter = f"%{q}%"
        stmt = stmt.filter(
            Challenge.title.ilike(q_filter) |
            Challenge.short_description.ilike(q_filter) |
            Challenge.subtitle.ilike(q_filter)
        )
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
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
        selected_persona_id=challenge.selected_persona_id,
        created_at=challenge.created_at if getattr(challenge, 'created_at', None) is not None else datetime.now()
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

async def get_daily_challenge(db: AsyncSession) -> Challenge | None:
    result = await db.execute(
        select(Challenge)
        .options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        )
        .filter(Challenge.for_user == True)
    )
    challenges = result.scalars().all()
    if not challenges:
        return None
        
    sorted_challenges = sorted(challenges, key=lambda c: c.id)
    today_str = datetime.utcnow().date().isoformat()
    hash_val = int(hashlib.md5(today_str.encode('utf-8')).hexdigest(), 16)
    index = hash_val % len(sorted_challenges)
    return sorted_challenges[index]

async def get_trending_challenges(db: AsyncSession, current_user_id: int) -> list[Challenge]:
    user_active_query = select(ChallengeSession.challenge_id).filter(
        ChallengeSession.user_id == current_user_id,
        ChallengeSession.status == 'active'
    )
    user_active_res = await db.execute(user_active_query)
    excluded_challenge_ids = [r[0] for r in user_active_res.all()]

    trending_query = (
        select(ChallengeSession.challenge_id, func.count(ChallengeSession.id).label('active_count'))
        .filter(
            ChallengeSession.status == 'active'
        )
    )
    if excluded_challenge_ids:
        trending_query = trending_query.filter(ChallengeSession.challenge_id.not_in(excluded_challenge_ids))
        
    trending_query = (
        trending_query.group_by(ChallengeSession.challenge_id)
        .order_by(desc(func.count(ChallengeSession.id)))
        .limit(5)
    )
    trending_res = await db.execute(trending_query)
    trending_ids = [r[0] for r in trending_res.all()]

    if not trending_ids:
        return []

    challenges_query = select(Challenge).options(
        selectinload(Challenge.context),
        selectinload(Challenge.selected_persona)
    ).filter(Challenge.id.in_(trending_ids))
    challenges_res = await db.execute(challenges_query)
    challenges_map = {c.id: c for c in challenges_res.scalars().all()}
    
    return [challenges_map[cid] for cid in trending_ids if cid in challenges_map]

async def get_recommended_challenges(db: AsyncSession, user_id: int | None = None) -> list[Challenge]:
    excluded_ids = []
    if user_id is not None:
        active_res = await db.execute(
            select(ChallengeSession.challenge_id).filter(
                ChallengeSession.user_id == user_id,
                ChallengeSession.status == 'active'
            )
        )
        active_ids = [r[0] for r in active_res.all()]

        attempts_res = await db.execute(
            select(ChallengeAttempt.challenge_id).filter(
                ChallengeAttempt.user_id == user_id
            )
        )
        attempt_ids = [r[0] for r in attempts_res.all()]

        excluded_ids = list(set(active_ids + attempt_ids))

    stmt = (
        select(Challenge)
        .options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        )
        .outerjoin(ChallengeAttempt, Challenge.id == ChallengeAttempt.challenge_id)
        .filter(Challenge.for_user == True)
    )
    
    if excluded_ids:
        stmt = stmt.filter(Challenge.id.not_in(excluded_ids))
        
    stmt = (
        stmt.group_by(Challenge.id)
        .order_by(desc(func.count(ChallengeAttempt.id)))
        .limit(5)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())

async def get_recently_added_challenges(db: AsyncSession) -> list[Challenge]:
    cutoff_time = datetime.now() - timedelta(hours=48)
    stmt = (
        select(Challenge)
        .options(
            selectinload(Challenge.context),
            selectinload(Challenge.selected_persona)
        )
        .filter(
            Challenge.for_user == True,
            Challenge.created_at.isnot(None),
            Challenge.created_at >= cutoff_time
        )
        .order_by(desc(Challenge.created_at))
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


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
    from datetime import datetime
    session = ChallengeSession(
        user_id=user_id,
        challenge_id=challenge_id,
        persona_id=persona_id,
        storyline=intro.storyline,
        call_to_action=intro.call_to_action,
        last_resumed_at=datetime.utcnow()
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