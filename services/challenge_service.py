from sqlalchemy.orm import Session
from app import models, schemas, crud

def get_all_challenges(db: Session):
    return crud.get_all_challenges(db)

def get_challenge_by_id(db: Session, challenge_id: str):
    return crud.get_challenge_by_id(db, challenge_id)

def create_or_update_challenge(db: Session, challenge_in: schemas.ChallengeCreate):
    return crud.upsert_challenge(db, challenge_in)

def get_challenge_context(db: Session, challenge_id: str):
    return crud.get_challenge_context_by_challenge_id(db, challenge_id)

# The rest of the file (e.g., generate_system_prompt) can be ported as needed from the old scenario_service.py
