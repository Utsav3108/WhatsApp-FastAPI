import json
import redis
from typing import Optional, Any
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
    value: Any,
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


def retrieve_cache(key: str) -> Optional[Any]:
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


def invalidate_cache(key: str):
    """
    Evicts a value from Redis.
    """
    try:
        redis_client.delete(key)
    except Exception as e:
      # print(f"Error invalidating cache key {key}: {e}")
      pass


# =============== Utility functions to create cache keys ===============

def create_persona_key(persona_id: int) -> str:
    """
    Creates a cache key for storing a specific persona's details.
    """
    return f"persona_{persona_id}"


def create_challenge_key(challenge_id: str) -> str:
    """
    Creates a cache key for storing a specific challenge's configuration.
    """
    return f"challenge_{challenge_id}"