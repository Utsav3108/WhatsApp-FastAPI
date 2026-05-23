from fastapi import FastAPI
from contextlib import asynccontextmanager
from app import models
from app.database import engine
import os
import json
from app.routes import router
from app.socketio_server import sio_app

from app import schemas, crud
from app.database import SessionLocal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
challenges_path = os.path.join(BASE_DIR, "challenge.json")

models.Base.metadata.create_all(bind=engine)

from contextlib import asynccontextmanager
import json
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------
    # Startup Logic
    # ------------------------------------------------------------

    # Load and upsert personas
    with open(file_path, "r", encoding="utf-8") as f:
        personas_data = json.load(f)

    with SessionLocal() as db:
        for persona in personas_data:
            persona_in = schemas.PersonaCreate(
                name=persona["name"],
                desc=persona["desc"],
                traits=persona["traits"],
                image_url=persona["image_url"],
            )
            crud.save_persona(db, persona_in)

    # Load and upsert challenges
    with open(challenges_path, "r", encoding="utf-8") as f:
        challenges_file_data = json.load(f)

    challenges = challenges_file_data.get("challenges", [])

    with SessionLocal() as db:
        for challenges in challenges:
            # Let Pydantic parse the entire nested JSON structure,
            # including context, difficulty_settings, challenge_rules, etc.
            challenges_in = schemas.ChallengeCreate.model_validate(challenges)

            # Create or update the challenges and its context
            crud.upsert_challenges(db, challenges_in)

    # ------------------------------------------------------------
    # Application Runs
    # ------------------------------------------------------------
    yield

    # ------------------------------------------------------------
    # Shutdown Logic (optional)
    # ------------------------------------------------------------

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(lifespan=lifespan)
app.include_router(router)


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

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO at /socket.io
app.mount("/socket.io", sio_app)
