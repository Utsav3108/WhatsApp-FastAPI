from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from google.genai.errors import ServerError, APIError

from app import schemas, models, crud
from app.database import get_db
from app.services import challenge_service
from app.services.challenge_session import setup_challenge_session
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("/challenges", response_model=list[schemas.ChallengeResponse])
async def get_all_challenges(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    challenges = await challenge_service.get_all_challenges(db, q=q, limit=limit, offset=offset)
    return challenges

@router.post("/challenges", response_model=schemas.ChallengeResponse)
async def create_challenge(challenge_in: schemas.ChallengeCreate, db: AsyncSession = Depends(get_db)):
    challenge = await challenge_service.create_or_update_challenge(db, challenge_in)
    return challenge

@router.post("/setup_challenge", response_model=schemas.ChallengeSetupResponse)
async def setup_challenge(
    request: schemas.ChallengeSetup = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: User ID does not match current user")
    try:
        print("Received challenge setup request")
        result = await setup_challenge_session(db, request)
        return result
        
    except ValueError as ve:
        return schemas.ChallengeSetupResponse(message=str(ve))
        
    except ServerError as se:
        print(f"Route caught ServerError: {se}")
        return schemas.ChallengeSetupResponse(
            message="The AI engine is currently overloaded. Please wait a moment and try again."
        )
        
    except APIError as ae:
        print(f"Route caught APIError: {ae}")
        return schemas.ChallengeSetupResponse(
            message="AI Service is temporarily unavailable. Please try again later."
        )
        
    except Exception as e:
        print(f"Unexpected System Error: {e}")
        return schemas.ChallengeSetupResponse(
            message="A system error occurred while setting up the challenge."
        )

@router.get("/challenge-attempts/{challenge_id}", response_model=list[schemas.ChallengeAttemptResponse])
async def get_challenge_attempts(
    challenge_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    attempts = await challenge_service.get_challenge_attempts(
        db, challenge_id, user_id=current_user.id, limit=limit, offset=offset
    )
    return attempts

@router.get("/challenge-sessions/active", response_model=list[schemas.ChallengeSessionResponse])
async def get_active_challenge_sessions(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    from sqlalchemy import select
    stmt = select(models.ChallengeSession).filter(
        models.ChallengeSession.user_id == current_user.id,
        models.ChallengeSession.status == "active"
    ).limit(limit).offset(offset)
    res = await db.execute(stmt)
    sessions = res.scalars().all()
    return sessions

@router.get("/challenges/dashboard", response_model=schemas.ChallengeDashboardResponse)
async def get_challenges_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    dashboard = await challenge_service.get_challenges_dashboard(db, current_user_id=current_user.id)
    return dashboard


@router.post("/challenge-sessions/{session_id}/pause")
async def pause_challenge_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    from datetime import datetime
    session = await crud.get_challenge_session_by_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Challenge session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    if session.status == 'active' and session.last_resumed_at:
        now = datetime.utcnow()
        delta = (now - session.last_resumed_at.replace(tzinfo=None)).total_seconds()
        session.elapsed_seconds += int(delta)
        session.last_resumed_at = None
        await db.commit()
        await db.refresh(session)
        
    return {"status": "success", "elapsed_seconds": session.elapsed_seconds}

