from typing import Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def get_latest_persona_session_id(db: AsyncSession, ai_persona_id: int, human_persona_id: int) -> Optional[int]:
    result = await db.execute(
        select(models.PersonaSessionModel.id)
        .where(models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        .where(models.PersonaSessionModel.human_persona_id == human_persona_id)
        .order_by(models.PersonaSessionModel.updated_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_persona_session_by_id(db: AsyncSession, persona_session_id: int) -> Optional[models.PersonaSessionModel]:
    return await db.get(models.PersonaSessionModel, persona_session_id)


async def get_latest_persona_session(db: AsyncSession, ai_persona_id: int, human_persona_id: int) -> Optional[models.PersonaSessionModel]:
    result = await db.execute(
        select(models.PersonaSessionModel)
        .where(models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        .where(models.PersonaSessionModel.human_persona_id == human_persona_id)
        .order_by(models.PersonaSessionModel.updated_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def create_persona_session(
    db: AsyncSession,
    *,
    ai_persona_id: int,
    human_persona_id: int,
    arousal: float,
    patience: float,
    mood: float,
    rapport: float,
    curiosity: float,
    last_subject: Optional[str],
    topic_repeat_streak: int,
    turn_count: int,
    violation_count: int,
    is_blocked: bool,
    block_reason: Optional[str],
) -> models.PersonaSessionModel:
    new_row = models.PersonaSessionModel(
        ai_persona_id=ai_persona_id,
        human_persona_id=human_persona_id,
        arousal=arousal,
        patience=patience,
        mood=mood,
        rapport=rapport,
        curiosity=curiosity,
        last_subject=last_subject,
        topic_repeat_streak=topic_repeat_streak,
        turn_count=turn_count,
        violation_count=violation_count,
        is_blocked=is_blocked,
        block_reason=block_reason,
    )
    db.add(new_row)
    await db.commit()
    await db.refresh(new_row)
    return new_row


async def update_persona_session(
    db: AsyncSession,
    session_id: int,
    *,
    arousal: float,
    patience: float,
    mood: float,
    rapport: float,
    curiosity: float,
    last_subject: Optional[str],
    topic_repeat_streak: int,
    turn_count: int,
    violation_count: int,
    is_blocked: bool,
    block_reason: Optional[str],
) -> None:
    await db.execute(
        sa_update(models.PersonaSessionModel)
        .where(models.PersonaSessionModel.id == session_id)
        .values(
            arousal=arousal,
            patience=patience,
            mood=mood,
            rapport=rapport,
            curiosity=curiosity,
            last_subject=last_subject,
            topic_repeat_streak=topic_repeat_streak,
            turn_count=turn_count,
            violation_count=violation_count,
            is_blocked=is_blocked,
            block_reason=block_reason,
        )
    )
    await db.commit()
