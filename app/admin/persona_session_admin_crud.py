from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update as sa_update, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import models


async def list_persona_session_pairs(
    db: AsyncSession,
    *,
    ai_persona_id: Optional[int] = None,
    human_persona_id: Optional[int] = None,
    has_blocked_fork: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    ps = models.PersonaSessionModel
    AiPersona = aliased(models.Persona)
    HumanPersona = aliased(models.Persona)

    # Derived from blocked_until, not the stored is_blocked column — admin
    # reads never go through PersonaSession.load()'s lazy-unblock path, so
    # is_blocked can go stale (stays True after blocked_until has already
    # passed, until a real chat message refreshes it). func.max(case(...))
    # instead of Postgres-only func.bool_or so this also works against the
    # SQLite in-memory test DB.
    now = datetime.now(timezone.utc)
    any_blocked_flag = func.max(
        case((ps.blocked_until.is_not(None) & (ps.blocked_until > now), 1), else_=0)
    )

    stmt = (
        select(
            ps.ai_persona_id,
            AiPersona.name.label("ai_persona_name"),
            ps.human_persona_id,
            HumanPersona.name.label("human_persona_name"),
            func.count(ps.id).label("fork_count"),
            any_blocked_flag.label("any_blocked_flag"),
            func.max(ps.updated_at).label("latest_updated_at"),
        )
        .join(AiPersona, AiPersona.id == ps.ai_persona_id)
        .join(HumanPersona, HumanPersona.id == ps.human_persona_id)
        .group_by(ps.ai_persona_id, AiPersona.name, ps.human_persona_id, HumanPersona.name)
    )

    if ai_persona_id is not None:
        stmt = stmt.filter(ps.ai_persona_id == ai_persona_id)
    if human_persona_id is not None:
        stmt = stmt.filter(ps.human_persona_id == human_persona_id)
    if has_blocked_fork is not None:
        stmt = stmt.having(any_blocked_flag > 0) if has_blocked_fork else stmt.having(any_blocked_flag == 0)

    stmt = stmt.order_by(func.max(ps.updated_at).desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.all()


async def get_forks_for_pair(db: AsyncSession, ai_persona_id: int, human_persona_id: int):
    result = await db.execute(
        select(models.PersonaSessionModel)
        .filter(
            models.PersonaSessionModel.ai_persona_id == ai_persona_id,
            models.PersonaSessionModel.human_persona_id == human_persona_id,
        )
        .order_by(models.PersonaSessionModel.updated_at.desc())
    )
    return result.scalars().all()


async def get_persona_session_detail(db: AsyncSession, session_id: int) -> Optional[models.PersonaSessionModel]:
    return await db.get(models.PersonaSessionModel, session_id)


async def count_linked_messages(db: AsyncSession, session_id: int) -> int:
    result = await db.execute(
        select(func.count(models.Message.id)).filter(models.Message.persona_session_id == session_id)
    )
    return result.scalar() or 0


async def reset_persona_session_block(db: AsyncSession, session_id: int) -> Optional[models.PersonaSessionModel]:
    await db.execute(
        sa_update(models.PersonaSessionModel)
        .where(models.PersonaSessionModel.id == session_id)
        .values(is_blocked=False, block_reason=None, violation_count=0, blocked_until=None)
    )
    await db.commit()
    return await db.get(models.PersonaSessionModel, session_id)
