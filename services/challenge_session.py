
from sqlalchemy.orm import Session
from app.crud_challenge_attempt import create_challenge_attempt

from app import crud, schemas
from app.services import persona_service, challenge_service
from app.gemini import create_storyline

def setup_challenge_session(db: Session, request: schemas.ChallengeSetup) -> schemas.ChallengeSetupResponse:
    if request.challenge_id is None:
        raise ValueError("challenge_id is required to start a challenge.")
    challenge = crud.get_challenge_by_id(db, request.challenge_id)
    if challenge.selected_persona:
        pass
    elif request.persona_id:
        persona = persona_service.get_persona_by_id(db, request.persona_id)
        challenge = challenge_service.assign_persona_to_challenge(
            db,
            request.challenge_id,
            persona.id
        )
    else:
        raise ValueError("No persona assigned to this challenge. Please provide a persona_id to assign.")
    existing_session = crud.get_active_session(
        db,
        request.user_id,
        request.challenge_id
    )
    if existing_session:
        return schemas.ChallengeSetupResponse(
            message="Challenge resumed successfully.",
            challenge_session_id=existing_session.id,
            intro=existing_session.storyline
        )
    storyline = create_storyline(challenge)
    session = crud.create_challenge_session(
        db=db,
        user_id=request.user_id,
        challenge_id=challenge.id,
        persona_id=challenge.selected_persona_id,
        storyline=storyline.storyline
    )
    return schemas.ChallengeSetupResponse(
        message=f"Challenge {challenge.title} started successfully.",
        challenge_session_id=session.id,
        intro=storyline,
        status=session.status,
        total_duration_minutes=challenge.estimated_duration_minutes
    )

def complete_challenge_session(db: Session, challenge_session_id: int, challenge_details = schemas.ChallengeCompletion):

    # STEP 1: Validate the challenge session and close it out in the DB.
    get_active_challenge_session = get_active_challenge_session(
        db, 
        session_id=challenge_session_id
    )
    

    session = crud.complete_session(
        db,
        get_active_challenge_session,
        "completed",
        challenge_details.reason
    )

    result = schemas.ChallengeCompletionResponse(message="Challenge session completed.", result_reason=session.result_reason)


    

    # STEP 2: Log the challenge details in the challenge attempts table for future analytics.
    # Fetch session details for logging
    persona_id = get_active_challenge_session.persona_id if hasattr(get_active_challenge_session, 'persona_id') else None
    user_id = get_active_challenge_session.user_id if hasattr(get_active_challenge_session, 'user_id') else None
    challenge_id = get_active_challenge_session.challenge_id if hasattr(get_active_challenge_session, 'challenge_id') else None
    role_mode = getattr(get_active_challenge_session, 'role_mode', None)
    # Calculate time taken (if available)
    time_taken_seconds = None
    if hasattr(get_active_challenge_session, 'started_at') and hasattr(get_active_challenge_session, 'completed_at') and get_active_challenge_session.completed_at and get_active_challenge_session.started_at:
        time_taken_seconds = int((get_active_challenge_session.completed_at - get_active_challenge_session.started_at).total_seconds())
    # Determine win status from challenge_details
    won = challenge_details.challenge_status == 'success' if hasattr(challenge_details, 'challenge_status') else False
    # Attempt number: count previous attempts (not implemented, set to 1 for now)
    attempt_number = 1
    create_challenge_attempt(
        db,
        challenge_id=challenge_id,
        user_id=user_id,
        persona_id=persona_id,
        role_mode=role_mode,
        won=won,
        time_taken_seconds=time_taken_seconds,
        attempt_number=attempt_number
    )
    return result

def get_active_challenge_session(db: Session, session_details: schemas.ChallengeCompletion):

    result = crud.get_active_session(
        db,
        session_details.user_id,
        session_details.challenge_id
    )

    if result:
        return result
    else:
        raise ValueError(f"No active challenge session found for user_id {session_details.user_id} and challenge_id {session_details.challenge_id}.")
