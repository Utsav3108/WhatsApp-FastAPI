from typing import Optional

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def list_personas(
    db: AsyncSession,
    *,
    name: Optional[str] = None,
    active_only: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(models.Persona).filter(models.Persona.is_human == False)
    if name:
        stmt = stmt.filter(models.Persona.name.ilike(f"%{name}%"))
    if active_only is not None:
        stmt = stmt.filter(models.Persona.is_active == active_only)
    stmt = stmt.order_by(models.Persona.name).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_persona(db: AsyncSession, persona_id: int) -> Optional[models.Persona]:
    return await db.get(models.Persona, persona_id)


async def create_persona(
    db: AsyncSession,
    *,
    name: str,
    desc: str,
    traits,
    image_url: str,
    category: Optional[str],
    email: Optional[str],
    role: Optional[str],
    bio: Optional[str],
    settings: Optional[dict],
    is_active: bool,
) -> models.Persona:
    row = models.Persona(
        name=name,
        desc=desc,
        traits=traits,
        image_url=image_url,
        is_human=False,
        category=category,
        email=email,
        role=role,
        bio=bio,
        settings=settings,
        is_active=is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_persona(db: AsyncSession, persona_id: int, **fields) -> Optional[models.Persona]:
    if fields:
        await db.execute(
            sa_update(models.Persona).where(models.Persona.id == persona_id).values(**fields)
        )
        await db.commit()
    return await get_persona(db, persona_id)


async def soft_delete_persona(db: AsyncSession, persona_id: int) -> Optional[models.Persona]:
    await db.execute(
        sa_update(models.Persona).where(models.Persona.id == persona_id).values(is_active=False)
    )
    await db.commit()
    return await get_persona(db, persona_id)
