from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def create_audit_log(
    db: AsyncSession,
    *,
    admin_id: int,
    action: str,
    target_type: str,
    target_id: str,
    detail: Optional[str] = None,
) -> models.AdminAuditLog:
    row = models.AdminAuditLog(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
