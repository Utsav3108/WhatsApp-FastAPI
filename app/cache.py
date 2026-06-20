import json
import redis
from typing import Optional
import dotenv

dotenv.load_dotenv()

REDIS_URL = dotenv.get_key(
    dotenv.find_dotenv(),
    "REDIS_URL"
)

redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True
)

print("Redis connection:", redis_client.ping())

# Default expiration time: 5 minutes (300 seconds)
DEFAULT_EXPIRY_SECONDS = 300


def store_cache(
    key: str,
    value: dict,
    expire_seconds: int = DEFAULT_EXPIRY_SECONDS
):
    """
    Stores a value in Redis as a JSON string.
    Compatible with all Redis providers.
    """

    redis_client.set(
        key,
        json.dumps(value),
        ex=expire_seconds
    )


def retrieve_cache(key: str) -> Optional[dict]:
    """
    Retrieves a value from Redis.
    Returns None if not found.
    """

    value = redis_client.get(key)

    if not value:
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


# =============== Utility functions to create cache keys ===============

def create_cache_message_key(
    user1_id: int,
    user2_id: int
) -> str:
    """
    Creates a cache key for storing messages between two users.
    The key is deterministic regardless of user order.
    """

    smaller_id, larger_id = sorted(
        [user1_id, user2_id]
    )

    return (
        f"conversation_"
        f"{smaller_id}_"
        f"{larger_id}"
    )


def create_personas_chat_key(
    user_id: int
) -> str:
    """
    Creates a cache key for storing the list
    of personas a user has chatted with.
    """

    return f"personas_chat_user_{user_id}"


def create_persona_search_key(
    query: str
) -> str:
    """
    Creates a cache key for persona search results.
    """

    return f"persona_search_{query.lower()}"