import redis
from typing import Optional

redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    decode_responses=True
)

# Default expiration time: 5 minutes (300 seconds)
DEFAULT_EXPIRY_SECONDS = 300


def store_cache(
    key: str,
    value: dict,
    expire_seconds: int = DEFAULT_EXPIRY_SECONDS
):
    
    """Stores a value in the cache with the given key and expiration time."""

    # Store JSON object
    redis_client.json().set(key, path="$", obj=value)

    # Set expiration time
    redis_client.expire(key, expire_seconds)


def retrieve_cache(key: str) -> Optional[dict]:

    """Retrieves a value from the cache by key. Returns None if not found."""   

    value = redis_client.json().get(key)

    if value:
        return value

    return None



# =============== Utility functions to create cache keys ===============

def create_cache_message_key(user1_id: int, user2_id: int) -> str:

    """Creates a cache key for storing messages between two users. 
    The key is deterministic regardless of the order of user IDs."""

    smaller_id, larger_id = sorted([user1_id, user2_id])
    return f"conversation_{smaller_id}_{larger_id}"


def create_presidents_chat_key(user_id: int) -> str:

    """Creates a cache key for storing the list of presidents a user has chatted with."""

    return f"presidents_chat_user_{user_id}"

def create_president_search_key(query: str) -> str:

    """Creates a cache key for storing search results for presidents based on a query."""

    return f"president_search_{query.lower()}"