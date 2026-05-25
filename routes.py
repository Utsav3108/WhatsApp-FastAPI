
# --- Storyline Endpoint ---
from requests import session
from starlette import status

from app.schemas import StorylineRequest, StorylineResponse
from fastapi import Body

from app import gemini


from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.s3_service import S3Service
from app import schemas, crud
from app.database import get_db
from app.AppServices.connection_manageer import ConnectionManager

from app.services import message_service, persona_service, challenge_service
from app.services.challenge_session import setup_challenge_session, complete_challenge_session

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
    "/setup_challenge",
    response_model=schemas.ChallengeSetupResponse
)
def setup_challenge(
    request: schemas.ChallengeSetup = Body(...),
    db: Session = Depends(get_db)
):
    try:
        return setup_challenge_session(db, request)
    except ValueError as ve:
        return schemas.ChallengeSetupResponse(message=str(ve))
    
# @router.post("/complete_challenge/{challenge_session_id}")
# def complete_challenge(
#     challenge_session_id: int,
#     challenge_completion: schemas.ChallengeCompletion = Body(...),  
#     db: Session = Depends(get_db)
# ):
#     try: 
#         result = complete_challenge_session(
#             db,
#             challenge_session_id,
#             challenge_completion.status,
#             challenge_completion.reason
#         )
#         return result
#     except ValueError as ve:
#         return schemas.ChallengeCompletionResponse(message=str(ve))