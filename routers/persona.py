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
