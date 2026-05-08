from fastapi import FastAPI
from contextlib import asynccontextmanager
import models
from database import engine
import os
import json
from routes import router
from socketio_server import sio_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "data.json")

models.Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: load presidents from data.json
    with open(file_path, "r") as f:
        data = json.load(f)
    import schemas, crud
    from database import SessionLocal
    for president in data:
        president_in = schemas.PresidentCreate(
            name=president["name"],
            desc=president["desc"],
            traits=president["traits"],
            image_url=president["image_url"]
        )
        with SessionLocal() as db:
            crud.save_president(db, president_in)
    yield
    # (Optional) Shutdown logic can go here


from fastapi.middleware.cors import CORSMiddleware

api = FastAPI(lifespan=lifespan)
api.include_router(router)

@api.get("/")
async def root():
    return {"message": "FastAPI is running"}

from fastapi.middleware.cors import CORSMiddleware
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Socket.IO at /socket.io
api.mount("/socket.io", sio_app)
