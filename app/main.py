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
from app.routers.conversations import router as conversations_router
from app.routers.reports import router as reports_router
from fastapi import Depends
from app.socketio_server import sio_app


import dotenv
dotenv.load_dotenv()

from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")
challenges_path = os.path.join(BASE_DIR, "challenge.json")

async def init_models():
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------
    # Startup Logic
    # ------------------------------------------------------------

    # Ensure models are created asynchronously
    await init_models()

    yield

    # ------------------------------------------------------------
    # Shutdown Logic (optional)
    # ------------------------------------------------------------

app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
app.include_router(persona_router, dependencies=[Depends(get_current_user)])
app.include_router(challenge_router, dependencies=[Depends(get_current_user)])
app.include_router(category_router, dependencies=[Depends(get_current_user)])
app.include_router(conversations_router, dependencies=[Depends(get_current_user)])
app.include_router(reports_router, dependencies=[Depends(get_current_user)])

allowed_origins = dotenv.get_key(dotenv.find_dotenv(), "ALLOWED_ORIGINS").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,        # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "FastAPI is running"}


# Mount Socket.IO at /socket.io
app.mount("/socket.io", sio_app)


from fastapi import FastAPI
from fastapi.responses import HTMLResponse

@app.get("/privacy", response_class=HTMLResponse)
async def read_privacy():
    with open("privacy.html", "r") as f:
        return f.read()