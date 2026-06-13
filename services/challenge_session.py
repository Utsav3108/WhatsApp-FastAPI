from sqlalchemy.ext.asyncio import AsyncSession
from app.crud_challenge_attempt import create_challenge_attempt
from app import crud, enums, schemas
from app.services import message_service, persona_service, challenge_service
from app.gemini import create_storyline

async def setup_challenge_session(
    db: AsyncSession,
    request: schemas.ChallengeSetup
) -> schemas.ChallengeSetupResponse:

    print(f"Setting up challenge session with request: {request}")

    if not request.challenge_id:
        raise ValueError("challenge_id is required to start a challenge.")

    challenge = await crud.get_challenge_by_id(db, request.challenge_id)

    # 1. Determine target persona ID and get target persona
    if challenge.selected_persona_id is not None:
        target_persona_id = challenge.selected_persona_id
        persona = challenge.selected_persona
    else:
        if not request.persona_id:
            raise ValueError(
                "No persona assigned to this challenge. "
                "Please provide a persona_id."
            )
        target_persona_id = request.persona_id
        persona = await persona_service.get_persona_by_id(db, target_persona_id)

    # -------------------------------------------------------------
    # Previous attempt requested explicitly
    # -------------------------------------------------------------
    if request.attempt_session_id:
        session = await crud.get_challenge_session_by_id(
            db,
            request.attempt_session_id
        )

        return await _build_existing_session_response(
            db=db,
            challenge=challenge,
            session=session,
            message="You have already completed this challenge. Here is your previous session history."
        )

    # -------------------------------------------------------------
    # Resume active session if available
    # -------------------------------------------------------------
    active_session = await crud.get_existing_session(
        db,
        request.user_id,
        challenge.id
    )

    if active_session:
        return await _build_existing_session_response(
            db=db,
            challenge=challenge,
            session=active_session,
            message="Resuming your existing challenge session."
        )
    
    # -------------------------------------------------------------
    # Create storyline if missing
    # -------------------------------------------------------------
    storyline = None

    if challenge.selected_persona_id is not None and challenge.context and challenge.context.storyline:
        storyline = schemas.StorylineResponse(
            storyline=challenge.context.storyline,
            call_to_action=challenge.context.call_to_action,
            end_goal=challenge.context.goal if challenge.context else None
        )
    else:
        print("Creating new storyline for challenge.")

        storyline = create_storyline(challenge, persona)
        if storyline and challenge.context and not getattr(storyline, 'end_goal', None):
            storyline.end_goal = challenge.context.goal

        # Only store storyline at the challenge level if it's a fixed-persona challenge
        if challenge.selected_persona_id is not None:
            await challenge_service.set_storyline(
                db,
                challenge.id,
                storyline
            )

    # -------------------------------------------------------------
    # Create new session
    # -------------------------------------------------------------
    session = await crud.create_challenge_session(
        db=db,
        user_id=request.user_id,
        challenge_id=challenge.id,
        persona_id=target_persona_id,
        intro=storyline
    )

    return schemas.ChallengeSetupResponse(
        message=f"Challenge '{challenge.title}' started successfully.",
        challenge_session_id=session.id,
        intro=storyline,
        status=session.status,
        total_duration_minutes=challenge.estimated_duration_minutes
    )


async def _build_existing_session_response(
    db: AsyncSession,
    challenge,
    session,
    message: str
) -> schemas.ChallengeSetupResponse:

    conversation_history = await message_service.get_message_by_session_id(
        db,
        session.id
    )

    intro = None

    if session.storyline:
        intro = schemas.StorylineResponse(
            storyline=session.storyline,
            call_to_action=session.call_to_action,
            end_goal=challenge.context.goal if challenge.context else None
        )

    return schemas.ChallengeSetupResponse(
        message=message,
        challenge_session_id=session.id,
        intro=intro,
        status=session.status,
        total_duration_minutes=challenge.estimated_duration_minutes,
        conversation_history=conversation_history
    )

async def complete_challenge_session(db: AsyncSession, challenge_details = schemas.ChallengeCompletion) -> schemas.ChallengeCompletionResponse:

    # Check if the session is already completed to avoid duplicate completion attempts
    session = await crud.get_challenge_session_by_id(db, challenge_details.challenge_session_id)
    if session and session.status != 'active':
        print(f"Challenge session {challenge_details.challenge_session_id} is already completed with status: {session.status}")
        return schemas.ChallengeCompletionResponse(
            message="Challenge session already completed.",
            challenge_status=session.status,
            result_reason=session.result_reason
        )

    # STEP 1: Validate the challenge session and close it out in the DB.
    active_challenge_session = await get_active_challenge_session(
        db, 
        session_details=challenge_details
    )
    

    session = await crud.complete_session(
        db,
        active_challenge_session,
        challenge_details.challenge_status,
        challenge_details.reason
    )


    # STEP 2: Log the challenge details in the challenge attempts table for future analytics.
    # Fetch session details for logging
    persona_id = active_challenge_session.persona_id if hasattr(active_challenge_session, 'persona_id') else None
    user_id = active_challenge_session.user_id if hasattr(active_challenge_session, 'user_id') else None
    challenge_id = active_challenge_session.challenge_id if hasattr(active_challenge_session, 'challenge_id') else None
    role_mode = getattr(active_challenge_session, 'role_mode', None)
    # Calculate time taken (if available)
    time_taken_seconds = None
    if hasattr(active_challenge_session, 'started_at') and hasattr(active_challenge_session, 'completed_at') and active_challenge_session.completed_at and active_challenge_session.started_at:
        time_taken_seconds = int((active_challenge_session.completed_at - active_challenge_session.started_at).total_seconds())
    # Determine win status from challenge_details

    print(f"Challenge completed with status: {challenge_details.challenge_status} and reason: {challenge_details.reason}")

    won = challenge_details.challenge_status == enums.ChallengeResult.WON_OBJECTIVE_COMPLETED or challenge_details.challenge_status == enums.ChallengeResult.WON if hasattr(challenge_details, 'challenge_status') else False
    # Attempt number: count previous attempts
    attempt_number = await challenge_service.get_attempt_number(db, challenge_id, user_id) + 1 if challenge_id and user_id else 1

    await create_challenge_attempt(
        db,
        challenge_id=challenge_id,
        user_id=user_id,
        persona_id=persona_id,
        role_mode=role_mode,
        won=won,
        time_taken_seconds=time_taken_seconds,
        attempt_number=attempt_number,
        challenge_session_id=challenge_details.challenge_session_id
    )

    print(f"Challenge session completed with status: {challenge_details.challenge_status} and reason: {challenge_details.reason}")

    
    result = schemas.ChallengeCompletionResponse(
        message="Challenge session completed.", 
        challenge_status=challenge_details.challenge_status, 
        result_reason=challenge_details.reason
        )

    return result

async def get_active_challenge_session(db: AsyncSession, session_details: schemas.ChallengeCompletion):

    result = await crud.get_existing_session(
        db,
        session_details.user_id,
        session_details.challenge_id
    )

    if result:
        return result
    else:
        raise ValueError(f"No active challenge session found for user_id {session_details.user_id} and challenge_id {session_details.challenge_id}.")
