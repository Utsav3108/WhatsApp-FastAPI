from app import crud, cache
from app.schemas import PersonaResponse, PersonaCreate
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
