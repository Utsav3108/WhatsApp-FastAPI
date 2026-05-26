
def get_challenge_attempts_by_challenge_id(db: Session, challenge_id: str):
    return db.query(models.ChallengeAttempt).filter(models.ChallengeAttempt.challenge_id == challenge_id).all()
from app import models
from sqlalchemy.orm import Session

def create_challenge_attempt(db: Session, *, challenge_id: str, user_id: int, persona_id: int, role_mode: str, won: bool, time_taken_seconds: int, attempt_number: int):
    db_attempt = models.ChallengeAttempt(
        challenge_id=challenge_id,
        user_id=user_id,
        persona_id=persona_id,
        role_mode=role_mode,
        won=won,
        time_taken_seconds=time_taken_seconds,
        attempt_number=attempt_number
    )
    db.add(db_attempt)
    db.commit()
    db.refresh(db_attempt)
    return db_attempt
