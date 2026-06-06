from app import crud, cache
from app.schemas import PersonaResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

async def get_persona_by_id(db: AsyncSession, persona_id: int):
    result = await crud.get_persona_by_id(db, persona_id)

    if result:
        return PersonaResponse.model_validate(result)
    else: 
        raise ValueError(f"Persona with ID {persona_id} not found.")

async def get_personas_user_chatted_with(db: AsyncSession, user_id: int):
    """Fetches the list of personas a user has chatted with.
    Checks the cache first before querying the database. If no personas are found, 
    returns Donald Trump as default."""

    key = cache.create_personas_chat_key(user_id=user_id)

    # Check cache first
    cached_personas = cache.retrieve_cache(key)
    if cached_personas is not None:
        print("Presidents retrieved from cache")
        return cached_personas
    
    # If not in cache, fetch from database
    personas = await crud.get_personas_user_chatted_with(db, user_id)

    if personas == []:
        persona = await crud.get_persona_by_name(db, "Donald Trump") # Default: Donald Trump
        personas = [persona] if persona else []
    
    personas_response = [PersonaResponse.model_validate(p).model_dump() for p in personas]

    # Cache the result for future requests
    cache.store_cache(key, personas_response)
    
    return personas_response

async def search_personas(db: AsyncSession, query: str):
    """Searches for personas based on a query string. Checks cache first before querying database."""

    key = cache.create_persona_search_key(query)

    # Check cache first
    cached_results = cache.retrieve_cache(key)
    if cached_results is not None:
        print("Search results retrieved from cache")
        return cached_results
    
    # If not in cache, fetch from database
    personas = await crud.search_personas(db, query)

    personas_response = [PersonaResponse.model_validate(p).model_dump() for p in personas]

    # Cache the result for future requests
    cache.store_cache(key, personas_response)

    return personas_response

async def get_all_personas(db: AsyncSession, limit: int = 50, offset: int = 0) -> List[PersonaResponse]:
    personas = await crud.get_all_personas(db, limit=limit, offset=offset)
    return [PersonaResponse.model_validate(p) for p in personas]