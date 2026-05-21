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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
scenario_path = os.path.join(BASE_DIR, "challenge.json")

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

    # Load and upsert scenarios
    with open(scenario_path, "r", encoding="utf-8") as f:
        scenario_file_data = json.load(f)

    scenarios = scenario_file_data.get("scenarios", [])

    with SessionLocal() as db:
        for scenario in scenarios:
            # Let Pydantic parse the entire nested JSON structure,
            # including context, difficulty_settings, challenge_rules, etc.
            scenario_in = schemas.ScenarioCreate.model_validate(scenario)

            # Create or update the scenario and its context
            crud.upsert_scenario(db, scenario_in)

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
