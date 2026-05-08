from app import crud, cache

from app.schemas import MessageResponse
from sqlalchemy.orm import Session
from typing import List

def get_messages_between_users(db, user1_id, user2_id, limit=50, offset=0) -> List[MessageResponse]:

    """Fetches messages between two users with pagination. Checks cache first before querying database."""

    key = cache.create_cache_message_key(user1_id, user2_id)

    # Check cache first
    cached_messages = cache.retrieve_cache(key)
    if cached_messages is not None:
        print("Messages retrieved from cache")
        return cached_messages
    
    # If not in cache, fetch from database
    messages = crud.get_messages_between_users(db, user1_id, user2_id, limit, offset)

    messages_response = [MessageResponse.model_validate(m).model_dump() for m in messages]

    # Cache the result for future requests
    cache.store_cache(key, messages_response)

    return messages_response
