# TODO(admin): challenge_sessions integration intentionally out of scope —
# see "app/claude_docs/Rippl Backend — Admin API Tasks.md" §C.

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.database import get_db
from app.admin.admin_auth import get_current_admin_user
from app.admin import persona_session_admin_service as ps_service
from app.admin import persona_admin_service as p_service

router = APIRouter(prefix="/admin", tags=["Admin"])


# --------------------------------------------------------------------------
# PersonaSession admin
# --------------------------------------------------------------------------

@router.get("/persona-sessions", response_model=list[schemas.AdminPersonaSessionPairListItem])
async def list_persona_session_pairs(
    has_blocked_fork: Optional[bool] = None,
    ai_persona_id: Optional[int] = None,
    human_persona_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    return await ps_service.list_pairs(
        db,
        ai_persona_id=ai_persona_id,
        human_persona_id=human_persona_id,
        has_blocked_fork=has_blocked_fork,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/persona-sessions/pairs/{ai_persona_id}/{human_persona_id}/forks",
    response_model=list[schemas.AdminPersonaSessionForkItem],
)
async def list_persona_session_forks(
    ai_persona_id: int,
    human_persona_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await ps_service.get_forks(db, ai_persona_id, human_persona_id)


@router.get("/persona-sessions/{session_id}", response_model=schemas.AdminPersonaSessionDetail)
async def get_persona_session_detail(session_id: int, db: AsyncSession = Depends(get_db)):
    detail = await ps_service.get_detail(db, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Persona session not found")
    return detail


@router.post("/persona-sessions/{session_id}/reset-block", response_model=schemas.AdminResetBlockResponse)
async def reset_persona_session_block(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    admin: models.Persona = Depends(get_current_admin_user),
):
    result = await ps_service.reset_block(db, session_id, admin_id=admin.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Persona session not found")
    return result


# --------------------------------------------------------------------------
# Persona admin
# --------------------------------------------------------------------------

@router.get("/personas", response_model=list[schemas.AdminPersonaListItem])
async def list_personas(
    name: Optional[str] = None,
    active_only: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    return await p_service.list_personas(db, name=name, active_only=active_only, limit=limit, offset=offset)


@router.get("/personas/{persona_id}", response_model=schemas.AdminPersonaDetail)
async def get_persona(persona_id: int, db: AsyncSession = Depends(get_db)):
    result = await p_service.get_persona(db, persona_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return result


@router.post("/personas", response_model=schemas.AdminPersonaDetail)
async def create_persona(persona_in: schemas.AdminPersonaCreate, db: AsyncSession = Depends(get_db)):
    return await p_service.create_persona(db, persona_in)


@router.put("/personas/{persona_id}", response_model=schemas.AdminPersonaDetail)
async def update_persona(
    persona_id: int,
    persona_in: schemas.AdminPersonaUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await p_service.update_persona(db, persona_id, persona_in)
    if result is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return result


@router.delete("/personas/{persona_id}", response_model=schemas.AdminPersonaDetail)
async def delete_persona(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    admin: models.Persona = Depends(get_current_admin_user),
):
    result = await p_service.soft_delete_persona(db, persona_id, admin_id=admin.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return result
