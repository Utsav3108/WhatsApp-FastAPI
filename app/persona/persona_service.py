import math
from datetime import datetime, timezone

from app import crud, cache
from app.schemas import (
    PersonaResponse,
    PersonaCreate,
    PersonaDetailsResponse,
    PersonaChatStatus,
    PersonaChatListItem,
    PersonaChatsResponse,
    StructuredTraits,
)
from app.persona import persona_session_crud
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

async def get_persona_by_id(db: AsyncSession, persona_id: int):
    # Check cache first
    key = cache.create_persona_key(persona_id)
    cached = cache.retrieve_cache(key)
    if cached:
      # print(f"Persona {persona_id} retrieved from cache")
        return PersonaResponse.model_validate(cached)

    result = await crud.get_persona_by_id(db, persona_id)

    if result:
        response = PersonaResponse.model_validate(result)
        # Store in cache (5 minutes)
        cache.store_cache(key, response.model_dump(mode="json"))
        return response
    else: 
        raise ValueError(f"Persona with ID {persona_id} not found.")

async def get_personas_user_chatted_with(db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0):
    """Fetches the list of personas a user has chatted with directly from the database. 
    If no personas are found, returns Donald Trump as default."""

    # Fetch from database directly
    personas = await crud.get_personas_user_chatted_with(db, user_id, limit=limit, offset=offset)

    if personas == []:
        persona = await crud.get_persona_by_name(db, "Donald Trump") # Default: Donald Trump
        personas = [persona] if persona else []
    
    return [PersonaResponse.model_validate(p).model_dump() for p in personas]

async def search_personas(db: AsyncSession, query: str, limit: int = 50, offset: int = 0):
    """Searches for personas based on a query string directly from the database."""

    # Fetch from database directly
    personas = await crud.search_personas(db, query, limit=limit, offset=offset)

    return [PersonaResponse.model_validate(p).model_dump() for p in personas]

async def get_all_personas(db: AsyncSession, limit: int = 50, offset: int = 0) -> List[PersonaResponse]:
    personas = await crud.get_all_personas(db, limit=limit, offset=offset)
    return [PersonaResponse.model_validate(p) for p in personas]

async def create_persona(db: AsyncSession, persona: PersonaCreate) -> PersonaResponse:
    db_persona = await crud.save_persona(db, persona)
    return PersonaResponse.model_validate(db_persona)

async def _get_ai_persona_or_404(db: AsyncSession, persona_id: int) -> PersonaResponse:
    """Shared lookup for persona-details-page endpoints: 404s (via ValueError,
    translated by the router) for a missing persona or one that's actually a
    human persona rather than an AI one."""
    try:
        persona = await get_persona_by_id(db, persona_id)
    except ValueError:
        raise ValueError(f"Persona with ID {persona_id} not found.")
    if persona.is_human:
        raise ValueError(f"Persona with ID {persona_id} not found.")
    return persona

async def get_persona_details(db: AsyncSession, persona_id: int) -> PersonaDetailsResponse:
    persona = await _get_ai_persona_or_404(db, persona_id)

    expertise = None
    likes_dislikes = None
    if isinstance(persona.traits, StructuredTraits):
        if persona.traits.interests_expertise:
            expertise = persona.traits.interests_expertise.expertise
        likes_dislikes = persona.traits.likes_dislikes

    return PersonaDetailsResponse(
        name=persona.name,
        desc=persona.desc,
        expertise=expertise,
        category=persona.category,
        likes_dislikes=likes_dislikes,
    )

def _is_effectively_blocked(session, now: datetime) -> bool:
    """Read-only equivalent of PersonaSession.load()'s blocked check, without
    the lazy-unblock decay/save side effects that path performs — mirrors the
    same blocked_until-only derivation used by the admin persona-session
    listing (is_blocked is not trusted here since it only gets refreshed by
    load())."""
    blocked_until = session.blocked_until
    if blocked_until is None:
        return False
    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    return blocked_until > now

async def get_persona_chats(
    db: AsyncSession,
    ai_persona_id: int,
    human_persona_id: int,
    page: int = 1,
    limit: int = 20,
) -> PersonaChatsResponse:
    await _get_ai_persona_or_404(db, ai_persona_id)

    recent = await persona_session_crud.get_latest_persona_session(db, ai_persona_id, human_persona_id)
    recent_id = recent.id if recent else None

    rows, total_count = await persona_session_crud.get_persona_sessions_paginated(
        db, ai_persona_id, human_persona_id, page=page, limit=limit
    )

    now = datetime.now(timezone.utc)
    chats = []
    for row in rows:
        if row.id == recent_id:
            status = PersonaChatStatus.recent
        elif _is_effectively_blocked(row, now):
            status = PersonaChatStatus.blocked
        else:
            status = PersonaChatStatus.active
        chats.append(PersonaChatListItem(
            persona_session_id=row.id,
            status=status,
            last_updated_at=row.updated_at,
        ))

    total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
    has_more = page < total_pages

    return PersonaChatsResponse(
        chats=chats,
        page=page,
        limit=limit,
        total_count=total_count,
        total_pages=total_pages,
        has_more=has_more,
    )
