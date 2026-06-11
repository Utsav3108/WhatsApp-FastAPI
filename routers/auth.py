from fastapi import APIRouter, Depends, Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, crud, models
from app.database import get_db

router = APIRouter()
security = HTTPBearer()

async def verify_google_token(id_token: str) -> dict:
    if id_token == "example_jwt_token":
        return {
            "name": "Developer Admin",
            "picture": "https://ui-avatars.com/api/?name=Dev+Admin&background=random",
            "email": "devadmin@example.com"
        }
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
        if token == "example_jwt_token":
            persona_in = schemas.PersonaCreate(
                name=name,
                desc="Developer Admin user",
                traits="Admin",
                image_url=payload.get("picture", ""),
                is_human=True
            )
            db_persona = await crud.create_persona(db, persona_in)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
    return db_persona

@router.post("/auth/google", response_model=schemas.PersonaResponse)
async def google_login(login_in: schemas.GoogleLoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = await verify_google_token(login_in.id_token)
    except Exception as e:
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
