from app import crud, cache
from app.schemas import PresidentResponse
from sqlalchemy.orm import Session
from typing import List

def get_presidents_user_chatted_with(db, user_id):

    """Fetches the list of presidents a user has chatted with.
    Checks the cache first before querying the database. If no presidents are found, 
    returns Donald Trump as default."""

    key = cache.create_presidents_chat_key(user_id=user_id)

    # Check cache first
    cached_presidents = cache.retrieve_cache(key)
    if cached_presidents is not None:
        print("Presidents retrieved from cache")
        return cached_presidents
    
    # If not in cache, fetch from database
    presidents = crud.get_presidents_user_chatted_with(db, user_id)


    if presidents == []:
        presidents = crud.get_president_by_name(db, "Donald Trump") # Default: Donald Trump
        presidents = [presidents] if presidents else []
    

    presidents_response = [PresidentResponse.model_validate(p).model_dump() for p in presidents]

    # Cache the result for future requests
    cache.store_cache(key, presidents_response)
    
    return presidents_response


def search_presidents(db: Session, query: str):

    """Searches for presidents based on a query string. Checks cache first before querying database."""

    key = cache.create_president_search_key(query)

    # Check cache first
    cached_results = cache.retrieve_cache(key)
    if cached_results is not None:
        print("Search results retrieved from cache")
        return cached_results
    
    # If not in cache, fetch from database
    presidents = crud.search_presidents(db, query)

    presidents_response = [PresidentResponse.model_validate(p).model_dump() for p in presidents]

    # Cache the result for future requests
    cache.store_cache(key, presidents_response)

    return presidents_response