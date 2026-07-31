from datetime import datetime
from typing import Optional

from sqlalchemy import select, update as sa_update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def get_latest_persona_session_id(db: AsyncSession, ai_persona_id: int, human_persona_id: int) -> Optional[int]:
    result = await db.execute(
        select(models.PersonaSessionModel.id)
        .where(models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        .where(models.PersonaSessionModel.human_persona_id == human_persona_id)
        # id.desc() as a tiebreaker: updated_at alone isn't strictly
        # ordered — SQLite's func.now() has only second resolution, and
        # even Postgres can tie under fast successive writes (e.g.
        # PersonaSession.create_new() immediately followed by a load() for
        # the same pair) — id.desc() deterministically favors the more
        # recently inserted row instead of an arbitrary tie order.
        .order_by(models.PersonaSessionModel.updated_at.desc(), models.PersonaSessionModel.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_persona_session_by_id(db: AsyncSession, persona_session_id: int) -> Optional[models.PersonaSessionModel]:
    return await db.get(models.PersonaSessionModel, persona_session_id)


async def get_persona_session_by_id_for_pair(
    db: AsyncSession,
    persona_session_id: int,
    ai_persona_id: int,
    human_persona_id: int,
) -> Optional[models.PersonaSessionModel]:
    """Ownership-checked-by-id lookup: returns the row only if its id AND
    (ai_persona_id, human_persona_id) all match, folded into one query
    (mirrors crud.get_messages_paginated_by_persona_session_id). Returns None
    both when the id doesn't exist and when it belongs to a different pair —
    the two cases are deliberately indistinguishable, since every caller
    treats either one as "reject," never as "fall back."
    """
    result = await db.execute(
        select(models.PersonaSessionModel)
        .where(models.PersonaSessionModel.id == persona_session_id)
        .where(models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        .where(models.PersonaSessionModel.human_persona_id == human_persona_id)
    )
    return result.scalars().first()


async def get_latest_persona_session(db: AsyncSession, ai_persona_id: int, human_persona_id: int) -> Optional[models.PersonaSessionModel]:
    result = await db.execute(
        select(models.PersonaSessionModel)
        .where(models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        .where(models.PersonaSessionModel.human_persona_id == human_persona_id)
        # id.desc() as a tiebreaker: updated_at alone isn't strictly
        # ordered — SQLite's func.now() has only second resolution, and
        # even Postgres can tie under fast successive writes (e.g.
        # PersonaSession.create_new() immediately followed by a load() for
        # the same pair) — id.desc() deterministically favors the more
        # recently inserted row instead of an arbitrary tie order.
        .order_by(models.PersonaSessionModel.updated_at.desc(), models.PersonaSessionModel.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_persona_sessions_paginated(
    db: AsyncSession,
    ai_persona_id: int,
    human_persona_id: int,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[models.PersonaSessionModel], int]:
    """Paginated fetch of every fork for an (ai_persona_id, human_persona_id)
    pair. Returns (rows, total_count), ordered most-recently-active first."""
    base_filter = (
        (models.PersonaSessionModel.ai_persona_id == ai_persona_id)
        & (models.PersonaSessionModel.human_persona_id == human_persona_id)
    )
    offset = (page - 1) * limit

    total_result = await db.execute(select(func.count(models.PersonaSessionModel.id)).filter(base_filter))
    total_count = total_result.scalar() or 0

    result = await db.execute(
        select(models.PersonaSessionModel)
        .filter(base_filter)
        .order_by(models.PersonaSessionModel.updated_at.desc(), models.PersonaSessionModel.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.scalars().all()
    return rows, total_count


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
    blocked_until: Optional[datetime],
    last_emotional_update_at: datetime,
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
        blocked_until=blocked_until,
        last_emotional_update_at=last_emotional_update_at,
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
    blocked_until: Optional[datetime],
    last_emotional_update_at: datetime,
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
            blocked_until=blocked_until,
            last_emotional_update_at=last_emotional_update_at,
        )
    )
    await db.commit()
