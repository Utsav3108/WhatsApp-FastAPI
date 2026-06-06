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

from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
challenges_path = os.path.join(BASE_DIR, "challenge.json")

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------
    # Startup Logic
    # ------------------------------------------------------------

    # Ensure models are created asynchronously
    await init_models()

    # Load and upsert personas
    with open(file_path, "r", encoding="utf-8") as f:
        personas_data = json.load(f)

    async with SessionLocal() as db:
        for persona in personas_data:
            persona_in = schemas.PersonaCreate(
                name=persona["name"],
                desc=persona["desc"],
                traits=persona["traits"],
                image_url=persona["image_url"],
            )
            await crud.save_persona(db, persona_in)

    yield

    # ------------------------------------------------------------
    # Shutdown Logic (optional)
    # ------------------------------------------------------------

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO at /socket.io
app.mount("/socket.io", sio_app)
