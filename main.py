from fastapi import FastAPI
from contextlib import asynccontextmanager
from app import models
from app.database import engine
import os
import json
from app.routers.auth import router as auth_router, get_current_user
from app.routers.persona import router as persona_router
from app.routers.challenge import router as challenge_router
from app.routers.category import router as category_router
from fastapi import Depends
from app.socketio_server import sio_app

from app import schemas, crud
from app.database import SessionLocal

from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
challenges_path = os.path.join(BASE_DIR, "challenge.json")

async def init_models():
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        # Migration: Add difficulty column if it doesn't exist in challenge_attempts
        if conn.dialect.name == "postgresql":
            await conn.execute(text("ALTER TABLE challenge_attempts ADD COLUMN IF NOT EXISTS difficulty VARCHAR;"))
        
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------
    # Startup Logic
    # ------------------------------------------------------------

    # Ensure models are created asynchronously
    await init_models()

    # Seed default categories if none exist
    async with SessionLocal() as db:
        existing_categories = await crud.get_all_categories(db)
        if not existing_categories:
            default_categories = [
                schemas.CategoryCreate(
                    name="Business & Career",
                    keywords=["Finance", "Business Strategy", "Startup", "Business"],
                    icon="business_center",
                    gradient_colors=["#0D47A1", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Social & Rapport",
                    keywords=["Social Skills", "Confidence", "Emotional Intelligence", "Conflict Resolution", "Empathy", "Social"],
                    icon="people",
                    gradient_colors=["#4A148C", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Dating",
                    keywords=["Dating"],
                    icon="favorite",
                    gradient_colors=["#B71C1C", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Leadership",
                    keywords=["Leadership"],
                    icon="star",
                    gradient_colors=["#E65100", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Negotiation",
                    keywords=["Negotiation"],
                    icon="handshake",
                    gradient_colors=["#004D40", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Politics",
                    keywords=["Politics", "Science"],
                    icon="gavel",
                    gradient_colors=["#1A237E", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Courtroom",
                    keywords=["Courtroom Drama", "Courtroom", "Critical Thinking"],
                    icon="balance",
                    gradient_colors=["#FFA000", "#000000"]
                ),
                schemas.CategoryCreate(
                    name="Entrepreneurship",
                    keywords=["Entrepreneurship", "Public Speaking", "Persuasion", "Startup"],
                    icon="lightbulb",
                    gradient_colors=["#BF360C", "#000000"]
                )
            ]
            for cat in default_categories:
                await crud.create_category(db, cat)

    # # Load and upsert personas
    # with open(file_path, "r", encoding="utf-8") as f:
    #     personas_data = json.load(f)

    # async with SessionLocal() as db:
    #     for persona in personas_data:
    #         persona_in = schemas.PersonaCreate(
    #             name=persona["name"],
    #             desc=persona["desc"],
    #             traits=persona["traits"],
    #             image_url=persona["image_url"],
    #             is_human=persona.get("is_human", False),
    #             category=persona.get("category", "Custom Creator")
    #         )
    #         await crud.save_persona(db, persona_in)

    yield

    # ------------------------------------------------------------
    # Shutdown Logic (optional)
    # ------------------------------------------------------------

app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(persona_router, dependencies=[Depends(get_current_user)])
app.include_router(challenge_router, dependencies=[Depends(get_current_user)])
app.include_router(category_router, dependencies=[Depends(get_current_user)])


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "FastAPI is running"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO at /socket.io
app.mount("/socket.io", sio_app)
