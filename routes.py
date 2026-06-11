# --- Storyline Endpoint ---
from requests import session
from starlette import status

from app.schemas import StorylineRequest, StorylineResponse
from fastapi import Body

from app import gemini


from fastapi import APIRouter, Depends, WebSocket, Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.s3_service import S3Service
from app import schemas, crud, models
from app.database import get_db
from app.AppServices.connection_manageer import ConnectionManager

from app.services import message_service, persona_service, challenge_service
from app.services.challenge_session import setup_challenge_session

public_router = APIRouter()
protected_router = APIRouter()
manager = ConnectionManager()


s3_service = S3Service()

def get_s3_service():
    return s3_service



@protected_router.get("/all-persona", response_model=list[schemas.PersonaResponse])
async def get_all_persona(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    personas = await persona_service.get_all_personas(db, limit=limit, offset=offset)
    return personas

@protected_router.post("/personas", response_model=schemas.PersonaResponse)
async def create_persona(persona_in: schemas.PersonaCreate, db: AsyncSession = Depends(get_db)):
    persona = await persona_service.create_persona(db, persona_in)
    return persona

async def verify_google_token(id_token: str) -> dict:
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}")
            if response.status_code == 200:
                return response.json()
    except ImportError:
        pass
    
    import requests
    response = requests.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}")
    if response.status_code == 200:
        return response.json()
    
    raise ValueError("Invalid Google ID Token")

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db)
) -> models.Persona:
    token = credentials.credentials
    try:
        payload = await verify_google_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}"
        )
    
    name = payload.get("name")
    if not name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: name not found"
        )
    
    db_persona = await crud.get_persona_by_name(db, name)
    if not db_persona:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return db_persona

@public_router.post("/auth/google", response_model=schemas.PersonaResponse)
async def google_login(login_in: schemas.GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = await verify_google_token(login_in.id_token)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
        
    name = payload.get("name", "Google User")
    image_url = payload.get("picture", "")
    
    db_persona = await crud.get_persona_by_name(db, name)
    if not db_persona:
        persona_in = schemas.PersonaCreate(
            name=name,
            desc="Google account user",
            traits="User",
            image_url=image_url,
            is_human=True
        )
        db_persona = await crud.create_persona(db, persona_in)
    return db_persona

@protected_router.get("/search-personas/{query}", response_model=list[schemas.PersonaResponse])
async def search_personas(query: str, db: AsyncSession = Depends(get_db)):
    response = await persona_service.search_personas(db, query)
    return response


@protected_router.get("/personas/{user_id}", response_model=list[schemas.PersonaResponse])
async def get_personas_user_chatted_with(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot access other user's chat history")
    response = await persona_service.get_personas_user_chatted_with(db, user_id)
    return response

@protected_router.get("/messages", response_model=list[schemas.MessageResponse])
async def get_messages(
    sender_id: int,
    receiver_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: Sender ID does not match current user")
    all_messages = await message_service.get_messages_between_users(db, sender_id, receiver_id, limit, offset)
    return all_messages 



@protected_router.get("/challenges", response_model=list[schemas.ChallengeResponse])
async def get_all_challenges(db: AsyncSession = Depends(get_db)):
    challenges = await challenge_service.get_all_challenges(db)
    return challenges




@protected_router.post("/challenges", response_model=schemas.ChallengeResponse)
async def create_challenge(challenge_in: schemas.ChallengeCreate, db: AsyncSession = Depends(get_db)):
    challenge = await challenge_service.create_or_update_challenge(db, challenge_in)
    return challenge



from google.genai.errors import ServerError, APIError

@protected_router.post(
    "/setup_challenge",
    response_model=schemas.ChallengeSetupResponse
)
async def setup_challenge(
    request: schemas.ChallengeSetup = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    if request.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: User ID does not match current user")
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

@protected_router.get("/challenge-attempts/{challenge_id}", response_model=list[schemas.ChallengeAttemptResponse])
async def get_challenge_attempts(
    challenge_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user)
):
    attempts = await challenge_service.get_challenge_attempts(db, challenge_id, user_id=current_user.id)
    return attempts
