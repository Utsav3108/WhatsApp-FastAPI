from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, cache
from app.admin import persona_admin_crud, admin_audit_crud


async def list_personas(
    db: AsyncSession,
    *,
    name: Optional[str] = None,
    active_only: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    rows = await persona_admin_crud.list_personas(db, name=name, active_only=active_only, limit=limit, offset=offset)
    return [schemas.AdminPersonaListItem.model_validate(r) for r in rows]


async def get_persona(db: AsyncSession, persona_id: int) -> Optional[schemas.AdminPersonaDetail]:
    row = await persona_admin_crud.get_persona(db, persona_id)
    return schemas.AdminPersonaDetail.model_validate(row) if row else None


async def create_persona(db: AsyncSession, persona_in: schemas.AdminPersonaCreate) -> schemas.AdminPersonaDetail:
    row = await persona_admin_crud.create_persona(
        db,
        name=persona_in.name,
        desc=persona_in.desc,
        traits=persona_in.traits,
        image_url=persona_in.image_url,
        category=persona_in.category,
        email=persona_in.email,
        role=persona_in.role,
        bio=persona_in.bio,
        settings=persona_in.settings,
        is_active=persona_in.is_active,
    )
    return schemas.AdminPersonaDetail.model_validate(row)


async def update_persona(
    db: AsyncSession, persona_id: int, persona_in: schemas.AdminPersonaUpdate
) -> Optional[schemas.AdminPersonaDetail]:
    existing = await persona_admin_crud.get_persona(db, persona_id)
    if existing is None:
        return None

    fields = persona_in.model_dump(exclude_unset=True)
    row = await persona_admin_crud.update_persona(db, persona_id, **fields)
    cache.invalidate_cache(cache.create_persona_key(persona_id))
    return schemas.AdminPersonaDetail.model_validate(row)


async def soft_delete_persona(
    db: AsyncSession, persona_id: int, *, admin_id: int
) -> Optional[schemas.AdminPersonaDetail]:
    existing = await persona_admin_crud.get_persona(db, persona_id)
    if existing is None:
        return None

    row = await persona_admin_crud.soft_delete_persona(db, persona_id)
    cache.invalidate_cache(cache.create_persona_key(persona_id))
    await admin_audit_crud.create_audit_log(
        db,
        admin_id=admin_id,
        action="persona_soft_delete",
        target_type="persona",
        target_id=str(persona_id),
    )
    return schemas.AdminPersonaDetail.model_validate(row)
