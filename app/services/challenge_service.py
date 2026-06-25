from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, crud, crud_challenge_attempt, cache

async def get_all_challenges(db: AsyncSession, q: str | None = None, limit: int = 50, offset: int = 0, for_user_only: bool = True) -> list[schemas.ChallengeResponse]:
    results = await crud.get_all_challenges(db, q=q, limit=limit, offset=offset, for_user_only=for_user_only)
    return [schemas.ChallengeResponse.model_validate(r) for r in results]

async def get_challenge_by_id(db: AsyncSession, challenge_id: str) -> schemas.ChallengeResponse | None:
    # Check cache first
    key = cache.create_challenge_key(challenge_id)
    cached = cache.retrieve_cache(key)
    if cached:
      # print(f"Challenge {challenge_id} retrieved from cache")
        return schemas.ChallengeResponse.model_validate(cached)

    result = await crud.get_challenge_by_id(db, challenge_id)
    if result:
        response = schemas.ChallengeResponse.model_validate(result)
        # Store in cache
        cache.store_cache(key, response.model_dump(mode="json"))
        return response
    return None

async def delete_challenge(db: AsyncSession, challenge_id: str) -> bool:
    challenge = await crud.get_challenge_by_id(db, challenge_id)
    if not challenge:
        return False
    await crud.delete_challenge(db, challenge_id)
    cache.invalidate_cache(cache.create_challenge_key(challenge_id))
    return True

async def create_or_update_challenge(db: AsyncSession, challenge_in: schemas.ChallengeCreate) -> schemas.ChallengeResponse:
    result = await crud.upsert_challenges(db, challenge_in)
    response = schemas.ChallengeResponse.model_validate(result)
    cache.invalidate_cache(cache.create_challenge_key(response.id))
    return response

async def get_challenge_context(db: AsyncSession, challenge_id: str):
    return await crud.get_challenge_context_by_challenge_id(db, challenge_id)

async def assign_persona_to_challenge(db: AsyncSession, challenge_id: str, persona_id: int) -> schemas.ChallengeResponse:
    challenge = await crud.get_challenge_by_id(db, challenge_id)
    if not challenge:
        raise ValueError(f"Challenge with ID {challenge_id} not found.")
    
    challenge.selected_persona_id = persona_id
    result = await crud.update_challenge(db, challenge)
    response = schemas.ChallengeResponse.model_validate(result)
    cache.invalidate_cache(cache.create_challenge_key(challenge_id))
    return response

async def set_storyline(db: AsyncSession, challenge_id: str, storyline: schemas.StorylineResponse) -> schemas.ChallengeResponse:
    challenge = await crud.get_challenge_by_id(db, challenge_id)
    if not challenge:
        raise ValueError(f"Challenge with ID {challenge_id} not found.")
    
    if not challenge.context:
        raise ValueError(f"Challenge with ID {challenge_id} does not have an associated context to update.")
    
    challenge.context.storyline = storyline.storyline
    challenge.context.call_to_action = storyline.call_to_action

    result = await crud.update_challenge(db, challenge)
    response = schemas.ChallengeResponse.model_validate(result)
    cache.invalidate_cache(cache.create_challenge_key(challenge_id))
    return response

async def get_challenge_attempts(db: AsyncSession, challenge_id: str, user_id: int = None, limit: int = 50, offset: int = 0) -> list[schemas.ChallengeAttemptResponse]:
    attempts = await crud_challenge_attempt.get_challenge_attempts_by_challenge_id(db, challenge_id, user_id, limit=limit, offset=offset)
    return [schemas.ChallengeAttemptResponse.model_validate(a) for a in attempts]

async def get_challenges_dashboard(db: AsyncSession, current_user_id: int) -> schemas.ChallengeDashboardResponse:
    daily = await crud.get_daily_challenge(db)
    if daily:
        attempts = await crud.get_attempts(db, user_id=current_user_id, challenge_id=daily.id)
        if any(a.won for a in attempts):
            daily = None

    trending = await crud.get_trending_challenges(db, current_user_id)
    recommended = await crud.get_recommended_challenges(db, user_id=current_user_id)
    recently_added = await crud.get_recently_added_challenges(db, user_id=current_user_id)
    
    return schemas.ChallengeDashboardResponse(
        daily_challenge=schemas.ChallengeResponse.model_validate(daily) if daily else None,
        trending_challenges=[schemas.ChallengeResponse.model_validate(t) for t in trending],
        recommended_challenges=[schemas.ChallengeResponse.model_validate(r) for r in recommended],
        recently_added_challenges=[schemas.ChallengeResponse.model_validate(ra) for ra in recently_added]
    )

import json

async def get_attempt_number(db: AsyncSession, challenge_id: str, user_id: int):
    attempt = await crud.get_attempts(db, user_id, challenge_id)
    return len(attempt)
