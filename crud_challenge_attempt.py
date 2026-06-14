from app import models
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def create_challenge_attempt(db: AsyncSession, *, challenge_id: str, user_id: int, persona_id: int, role_mode: str, won: bool, time_taken_seconds: int, attempt_number: int, challenge_session_id: int = None):
    db_attempt = models.ChallengeAttempt(
        challenge_id=challenge_id,
        user_id=user_id,
        persona_id=persona_id,
        role_mode=role_mode,
        won=won,
        time_taken_seconds=time_taken_seconds,
        attempt_number=attempt_number,
        challenge_session_id=challenge_session_id
    )
    db.add(db_attempt)
    await db.commit()
    await db.refresh(db_attempt)
    return db_attempt

async def get_challenge_attempts_by_challenge_id(db: AsyncSession, challenge_id: str, user_id: int = None, limit: int = 50, offset: int = 0):
    query = select(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id == challenge_id)
    if user_id is not None:
        query = query.filter(models.ChallengeAttempt.user_id == user_id)
    query = query.order_by(models.ChallengeAttempt.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()
