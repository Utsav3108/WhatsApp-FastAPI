import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Redis caching functions.
def store_cache(key: str, value: dict):

    redis_client.json().set(key, path="$", obj=value)  # Store the JSON string in Redis


def retrieve_cache(key: str) -> dict:
    value = redis_client.json().get(key)  # Retrieve the JSON string from Redis
    if value:
        return value
    
    return None
