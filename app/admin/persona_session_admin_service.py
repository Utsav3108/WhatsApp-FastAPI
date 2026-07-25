from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.admin import persona_session_admin_crud, admin_audit_crud


def _is_currently_blocked(blocked_until) -> bool:
    """Derives "genuinely blocked right now" from blocked_until rather than
    trusting the stored is_blocked column, which can go stale between chat
    turns (only PersonaSession.load()'s lazy-unblock path refreshes it).
    Both sides normalized to naive UTC before comparing — SQLite drops
    tzinfo on read-back even for DateTime(timezone=True) columns (Postgres
    doesn't), so a raw aware-vs-naive comparison would raise under the
    SQLite-backed test suite."""
    if blocked_until is None:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return blocked_until.replace(tzinfo=None) > now


async def list_pairs(
    db: AsyncSession,
    *,
    ai_persona_id: Optional[int] = None,
    human_persona_id: Optional[int] = None,
    has_blocked_fork: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    rows = await persona_session_admin_crud.list_persona_session_pairs(
        db,
        ai_persona_id=ai_persona_id,
        human_persona_id=human_persona_id,
        has_blocked_fork=has_blocked_fork,
        limit=limit,
        offset=offset,
    )
    return [
        schemas.AdminPersonaSessionPairListItem(
            ai_persona_id=r.ai_persona_id,
            ai_persona_name=r.ai_persona_name,
            human_persona_id=r.human_persona_id,
            human_persona_name=r.human_persona_name,
            fork_count=r.fork_count,
            any_fork_blocked=bool(r.any_blocked_flag),
            latest_updated_at=r.latest_updated_at,
        )
        for r in rows
    ]


async def get_forks(db: AsyncSession, ai_persona_id: int, human_persona_id: int):
    rows = await persona_session_admin_crud.get_forks_for_pair(db, ai_persona_id, human_persona_id)
    return [
        schemas.AdminPersonaSessionForkItem(
            id=r.id,
            is_blocked=_is_currently_blocked(r.blocked_until),
            block_reason=r.block_reason,
            blocked_until=r.blocked_until,
            turn_count=r.turn_count,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


async def get_detail(db: AsyncSession, session_id: int) -> Optional[schemas.AdminPersonaSessionDetail]:
    row = await persona_session_admin_crud.get_persona_session_detail(db, session_id)
    if row is None:
        return None
    linked_message_count = await persona_session_admin_crud.count_linked_messages(db, session_id)
    return schemas.AdminPersonaSessionDetail(
        id=row.id,
        ai_persona_id=row.ai_persona_id,
        human_persona_id=row.human_persona_id,
        arousal=row.arousal,
        patience=row.patience,
        mood=row.mood,
        rapport=row.rapport,
        curiosity=row.curiosity,
        last_subject=row.last_subject,
        topic_repeat_streak=row.topic_repeat_streak,
        turn_count=row.turn_count,
        violation_count=row.violation_count,
        is_blocked=_is_currently_blocked(row.blocked_until),
        block_reason=row.block_reason,
        blocked_until=row.blocked_until,
        created_at=row.created_at,
        updated_at=row.updated_at,
        linked_message_count=linked_message_count,
    )


async def reset_block(
    db: AsyncSession, session_id: int, *, admin_id: int
) -> Optional[schemas.AdminResetBlockResponse]:
    existing = await persona_session_admin_crud.get_persona_session_detail(db, session_id)
    if existing is None:
        return None

    updated = await persona_session_admin_crud.reset_persona_session_block(db, session_id)
    await admin_audit_crud.create_audit_log(
        db,
        admin_id=admin_id,
        action="reset_block",
        target_type="persona_session",
        target_id=str(session_id),
        detail=(
            f"was_blocked={existing.is_blocked}, "
            f"block_reason={existing.block_reason!r}, "
            f"violation_count={existing.violation_count}"
        ),
    )
    return schemas.AdminResetBlockResponse.model_validate(updated)
