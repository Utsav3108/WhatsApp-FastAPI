from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models, crud
from app.database import get_db
from app.services import message_service
from app.routers.auth import get_current_user
from app.persona import persona_service, persona_crud

router = APIRouter(tags=["Persona"])

@router.get("/all-persona", response_model=list[schemas.PersonaResponse])
async def get_all_persona(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    personas = await persona_service.get_all_personas(db, limit=limit, offset=offset)
    return personas

@router.post("/personas", response_model=schemas.PersonaResponse)
async def create_persona(persona_in: schemas.PersonaCreate, db: AsyncSession = Depends(get_db)):
    persona = await persona_service.create_persona(db, persona_in)
    return persona

@router.get("/search-personas/{query}", response_model=list[schemas.PersonaResponse])
async def search_personas(
    query: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    response = await persona_service.search_personas(db, query, limit=limit, offset=offset)
    return response

@router.get("/personas/{user_id}", response_model=list[schemas.PersonaResponse])
async def get_personas_user_chatted_with(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access other user's chat history")
    response = await persona_service.get_personas_user_chatted_with(db, user_id, limit=limit, offset=offset)
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

@router.get("/profile", response_model=schemas.UserProfileResponse)
async def get_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    # 1. Total challenges attempted & Success rate
    attempts = await persona_crud.get_challenge_attempts_by_user(db, current_user.id)
    total_challenges_attempted = len(attempts)

    total_wins = sum(1 for a in attempts if a.won)
    success_rate = (total_wins / total_challenges_attempted) * 100.0 if total_challenges_attempted > 0 else 0.0

    # 2. Total practice sessions
    practice_persona_ids = await persona_crud.get_practice_partner_persona_ids(db, current_user.id)
    total_practice_sessions = len(practice_persona_ids)

    # 3. Attempt logs
    rows = await persona_crud.get_recent_attempts_log(db, current_user.id, limit=5)
    attempts_log = []
    for attempt, challenge_title, persona_name in rows:
        attempts_log.append(schemas.ProfileAttemptLogItem(
            challenge_id=attempt.challenge_id,
            challenge_title=challenge_title,
            persona_name=persona_name,
            won=attempt.won,
            created_at=attempt.created_at,
            challenge_session_id=attempt.challenge_session_id,
            persona_id=attempt.persona_id
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

@router.delete("/profile")
async def delete_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    await persona_crud.delete_user_account_cascade(db, current_user.id)
    return {"message": "Account and all associated data deleted successfully."}
