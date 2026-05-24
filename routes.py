
# --- Storyline Endpoint ---
from app.schemas import ChallengeStartResponse, StorylineRequest, StorylineResponse
from fastapi import Body

from app import gemini


from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.s3_service import S3Service
from app import schemas, crud
from app.database import get_db
from app.AppServices.connection_manageer import ConnectionManager

from app.services import message_service, persona_service, challenge_service

router = APIRouter()
manager = ConnectionManager()


s3_service = S3Service()

def get_s3_service():
    return s3_service



@router.get("/all-persona", response_model=list[schemas.PersonaResponse])
def get_all_persona(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    personas = crud.get_all_personas(db, limit=limit, offset=offset)
    return personas

@router.get("/search-personas/{query}", response_model=list[schemas.PersonaResponse])
def search_personas(query: str, db: Session = Depends(get_db)):
    response = persona_service.search_personas(db, query)
    return response


@router.get("/personas/{user_id}", response_model=list[schemas.PersonaResponse])
def get_personas_user_chatted_with(user_id: int, db: Session = Depends(get_db)):
    response = persona_service.get_personas_user_chatted_with(db, user_id)
    return response

@router.get("/messages", response_model=list[schemas.MessageResponse])
def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    all_messages = message_service.get_messages_between_users(db, sender_id, receiver_id, limit, offset)

    return all_messages 



@router.get("/challenges", response_model=list[schemas.ChallengeResponse])
def get_all_challenges(db: Session = Depends(get_db)):
    challenges = challenge_service.get_all_challenges(db)
    return challenges




@router.post("/challenges", response_model=schemas.ChallengeResponse)
def create_challenge(challenge_in: schemas.ChallengeCreate, db: Session = Depends(get_db)):
    challenge = challenge_service.create_or_update_challenge(db, challenge_in)
    return challenge



@router.post(
    "/start_challenge",
    response_model=schemas.ChallengeStartResponse
)
def start_challenge(
    request: schemas.ChallengeStartRequest = Body(...),
    db: Session = Depends(get_db)
):

    try:
    
        persona = crud.get_persona_by_id(
            db,
            request.persona_id
        )

        if not persona:
            raise ValueError(
                f"Persona with ID {request.persona_id} not found.",

            )

        existing_session = crud.get_active_session(
            db,
            request.user_id,
            request.challenge_id
        )

        # Resume existing challenge
        if existing_session:

            return schemas.ChallengeStartResponse(
                message="Challenge resumed successfully.",
                challenge_session_id=existing_session.id,
                intro=existing_session.storyline,
                expires_at=existing_session.expires_at
            )

        challenge = challenge_service.assign_persona_to_challenge(
            db,
            request.challenge_id,
            persona.id
        )

        storyline : StorylineResponse = gemini.create_storyline(challenge)

        session = crud.create_challenge_session(
            db=db,
            user_id=request.user_id,
            challenge_id=challenge.id,
            persona_id=persona.id,
            storyline=storyline.storyline
        )

        

        return schemas.ChallengeStartResponse(
            message=f"Challenge {challenge.title} started successfully.",
            challenge_session_id=session.id,    
            intro=storyline,
            status=session.status,
            expires_at=session.expires_at.isoformat()
        )

    except ValueError as ve:
        return ChallengeStartResponse(
            message=str(ve)
        )