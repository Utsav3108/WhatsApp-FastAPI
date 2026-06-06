from app import crud, cache
from app.schemas import MessageResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

async def get_messages_between_users(db: AsyncSession, user1_id: int, user2_id: int, limit: int = 50, offset: int = 0) -> List[MessageResponse]:
    """Fetches messages between two users with pagination. Checks cache first before querying database."""

    key = cache.create_cache_message_key(user1_id, user2_id)

    # Check cache first
    cached_messages = cache.retrieve_cache(key)
    if cached_messages is not None:
        print("Messages retrieved from cache")
        return cached_messages
    
    # If not in cache, fetch from database
    messages = await crud.get_messages_between_users(db, user1_id, user2_id, limit, offset)

    messages_response = [MessageResponse.model_validate(m).model_dump() for m in messages]

    # Cache the result for future requests
    cache.store_cache(key, messages_response)

    return messages_response

async def get_message_by_session_id(db: AsyncSession, challenge_session_id: int) -> List[MessageResponse]:
    messages = await crud.get_messages_by_challenge_session_id(db, challenge_session_id)
    return [MessageResponse.model_validate(m) for m in messages]