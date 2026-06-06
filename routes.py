# --- Storyline Endpoint ---
from requests import session
from starlette import status

from app.schemas import StorylineRequest, StorylineResponse
from fastapi import Body

from app import gemini


from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.s3_service import S3Service
from app import schemas, crud
from app.database import get_db
from app.AppServices.connection_manageer import ConnectionManager

from app.services import message_service, persona_service, challenge_service
from app.services.challenge_session import setup_challenge_session

router = APIRouter()
manager = ConnectionManager()


s3_service = S3Service()

def get_s3_service():
    return s3_service



@router.get("/all-persona", response_model=list[schemas.PersonaResponse])
async def get_all_persona(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    personas = await persona_service.get_all_personas(db, limit=limit, offset=offset)
    return personas

@router.get("/search-personas/{query}", response_model=list[schemas.PersonaResponse])
async def search_personas(query: str, db: AsyncSession = Depends(get_db)):
    response = await persona_service.search_personas(db, query)
    return response


@router.get("/personas/{user_id}", response_model=list[schemas.PersonaResponse])
async def get_personas_user_chatted_with(user_id: int, db: AsyncSession = Depends(get_db)):
    response = await persona_service.get_personas_user_chatted_with(db, user_id)
    return response

@router.get("/messages", response_model=list[schemas.MessageResponse])
async def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    all_messages = await message_service.get_messages_between_users(db, sender_id, receiver_id, limit, offset)
    return all_messages 



@router.get("/challenges", response_model=list[schemas.ChallengeResponse])
async def get_all_challenges(db: AsyncSession = Depends(get_db)):
    challenges = await challenge_service.get_all_challenges(db)
    return challenges




@router.post("/challenges", response_model=schemas.ChallengeResponse)
async def create_challenge(challenge_in: schemas.ChallengeCreate, db: AsyncSession = Depends(get_db)):
    challenge = await challenge_service.create_or_update_challenge(db, challenge_in)
    return challenge



from google.genai.errors import ServerError, APIError

@router.post(
    "/setup_challenge",
    response_model=schemas.ChallengeSetupResponse
)
async def setup_challenge(
    request: schemas.ChallengeSetup = Body(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        print("""Received challenge setup request""")
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
async def get_challenge_attempts(challenge_id: str, db: AsyncSession = Depends(get_db)):
    attempts = await challenge_service.get_challenge_attempts(db, challenge_id)
    return attempts
