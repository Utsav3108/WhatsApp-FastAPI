from fastapi import FastAPI
from contextlib import asynccontextmanager
from app import models
from app.database import engine
import os
import json
from app.routers.auth import router as auth_router, get_current_user
from app.routers.persona import router as persona_router
from app.routers.challenge import router as challenge_router
from fastapi import Depends
from app.socketio_server import sio_app

from app import schemas, crud
from app.database import SessionLocal

from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
challenges_path = os.path.join(BASE_DIR, "challenge.json")

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN is_human BOOLEAN DEFAULT 0;"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE challenges ADD COLUMN created_at DATETIME;"))
            print("Successfully added created_at column to challenges table")
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN category VARCHAR DEFAULT 'Custom Creator';"))
            print("Successfully added category column to personas table")
        except Exception as e:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN email VARCHAR;"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN role VARCHAR;"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN bio VARCHAR;"))
        except Exception:
            pass
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE personas ADD COLUMN settings TEXT;"))
        except Exception:
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------
    # Startup Logic
    # ------------------------------------------------------------

    # Ensure models are created asynchronously
    await init_models()

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
