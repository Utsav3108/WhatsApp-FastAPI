from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models
from app.database import get_db
from app.services import persona_service, message_service
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("/all-persona", response_model=list[schemas.PersonaResponse])
async def get_all_persona(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    personas = await persona_service.get_all_personas(db, limit=limit, offset=offset)
    return personas

@router.post("/personas", response_model=schemas.PersonaResponse)
async def create_persona(persona_in: schemas.PersonaCreate, db: AsyncSession = Depends(get_db)):
    persona = await persona_service.create_persona(db, persona_in)
    return persona

@router.get("/search-personas/{query}", response_model=list[schemas.PersonaResponse])
async def search_personas(query: str, db: AsyncSession = Depends(get_db)):
    response = await persona_service.search_personas(db, query)
    return response

@router.get("/personas/{user_id}", response_model=list[schemas.PersonaResponse])
async def get_personas_user_chatted_with(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access other user's chat history")
    response = await persona_service.get_personas_user_chatted_with(db, user_id)
    return response

@router.get("/messages", response_model=list[schemas.MessageResponse])
async def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: Sender ID does not match current user")
    all_messages = await message_service.get_messages_between_users(db, sender_id, receiver_id, limit, offset)
    return all_messages

from sqlalchemy import select
from app import crud

@router.get("/profile", response_model=schemas.UserProfileResponse)
async def get_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    # 1. Total challenges attempted & Success rate
    stmt_attempts = select(models.ChallengeAttempt).filter(models.ChallengeAttempt.user_id == current_user.id)
    res_attempts = await db.execute(stmt_attempts)
    attempts = res_attempts.scalars().all()
    total_challenges_attempted = len(attempts)
    
    total_wins = sum(1 for a in attempts if a.won)
    success_rate = (total_wins / total_challenges_attempted) * 100.0 if total_challenges_attempted > 0 else 0.0
    
    # 2. Total practice sessions
    sent_res = await db.execute(
        select(models.Message.receiver_id)
        .filter(models.Message.sender_id == current_user.id, models.Message.challenge_session_id == None)
        .distinct()
    )
    received_res = await db.execute(
        select(models.Message.sender_id)
        .filter(models.Message.receiver_id == current_user.id, models.Message.challenge_session_id == None)
        .distinct()
    )
    sent_to_personas = [row[0] for row in sent_res.all()]
    received_from_personas = [row[0] for row in received_res.all()]
    practice_persona_ids = list(set(sent_to_personas + received_from_personas))
    total_practice_sessions = len(practice_persona_ids)
    
    # 3. Attempt logs
    stmt_log = (
        select(models.ChallengeAttempt, models.Challenge.title, models.Persona.name)
        .join(models.Challenge, models.ChallengeAttempt.challenge_id == models.Challenge.id)
        .join(models.Persona, models.ChallengeAttempt.persona_id == models.Persona.id)
        .filter(models.ChallengeAttempt.user_id == current_user.id)
        .order_by(models.ChallengeAttempt.created_at.desc())
        .limit(5)
    )
    res_log = await db.execute(stmt_log)
    rows = res_log.all()
    attempts_log = []
    for attempt, challenge_title, persona_name in rows:
        attempts_log.append(schemas.ProfileAttemptLogItem(
            challenge_id=attempt.challenge_id,
            challenge_title=challenge_title,
            persona_name=persona_name,
            won=attempt.won,
            created_at=attempt.created_at,
            challenge_session_id=attempt.challenge_session_id
        ))
        
    return schemas.UserProfileResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        bio=current_user.bio,
        image_url=current_user.image_url,
        settings=current_user.settings,
        stats=schemas.ProfileStats(
            total_challenges_attempted=total_challenges_attempted,
            success_rate_percentage=success_rate,
            total_practice_sessions=total_practice_sessions
        ),
        attempts_log=attempts_log
    )

@router.put("/profile", response_model=schemas.PersonaResponse)
async def update_user_profile(
    profile_in: schemas.UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    updated_user = await crud.update_user_profile(db, current_user.id, profile_in)
    return updated_user
