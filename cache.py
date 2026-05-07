import redis
from typing import Optional

redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    decode_responses=True
)

# Default expiration time: 1 hour
DEFAULT_EXPIRY_SECONDS = 60 * 60


def store_cache(
    key: str,
    value: dict,
    expire_seconds: int = DEFAULT_EXPIRY_SECONDS
):
    # Store JSON object
    redis_client.json().set(key, path="$", obj=value)

    # Set expiration time
    redis_client.expire(key, expire_seconds)


def retrieve_cache(key: str) -> Optional[dict]:
    value = redis_client.json().get(key)

    if value:
        return value

    return None


def create_cache_message_key(user1_id: int, user2_id: int) -> str:
    smaller_id, larger_id = sorted([user1_id, user2_id])
    return f"conversation_{smaller_id}_{larger_id}"


def create_cache_president_key(president_id: int, user_id: int) -> str:
    return f"president_{president_id}_user_{user_id}"