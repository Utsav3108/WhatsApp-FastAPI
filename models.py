import uuid

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON, Enum, UniqueConstraint
from app.database import Base
from sqlalchemy import DateTime
from datetime import datetime, timezone
import enum

from sqlalchemy.dialects.postgresql import UUID, JSONB


# ChallengeContext table
from sqlalchemy.orm import relationship




# ChallengeAttempt table
class ChallengeAttempt(Base):
    __tablename__ = "challenge_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_id = Column(String, ForeignKey("challenges.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("personas.id"), nullable=False)  # Now references Persona
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False)
    role_mode = Column(String)
    won = Column(Boolean, nullable=False)
    score = Column(Integer)
    number_of_turns = Column(Integer)
    time_taken_seconds = Column(Integer)
    attempt_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    user = relationship("Persona", foreign_keys=[user_id])
    challenge = relationship("Challenge")
    persona = relationship("Persona", foreign_keys=[persona_id])

class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    desc = Column(String)
    traits = Column(String)
    image_url = Column(String, default="")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("personas.id"))
    receiver_id = Column(Integer, ForeignKey("personas.id"))
    text = Column(String)
    is_user = Column(Boolean)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    image_object_name = Column(String, nullable=True)





class ChallengeContext(Base):
    __tablename__ = "challenge_contexts"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(String, ForeignKey("challenges.id"), unique=True)
    setting = Column(String)
    environment = Column(JSON, nullable=True)  # Optional, JSON type
    goal = Column(String)
    stakes = Column(String)
    platform = Column(String)
    challenge = relationship("Challenge", back_populates="context")




# Enum for challenge difficulty
class ChallengeDifficulty(enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advance = "advance"


class Challenge(Base):
    __tablename__ = "challenges"

    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    subtitle = Column(String, nullable=True)
    description = Column(String, nullable=True)
    short_description = Column(String, nullable=True)
    categories = Column(JSON, nullable=True)
    suggested_personas = Column(JSON, nullable=True)
    difficulty = Column(Enum(ChallengeDifficulty), nullable=True)
    difficulty_settings = Column(JSON, nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    challenge_rules = Column(JSON, nullable=True)
    image_url = Column(String, nullable=True)
    context = relationship("ChallengeContext", uselist=False, back_populates="challenge", cascade="all, delete-orphan")

    selected_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True)  # New field for selected persona
    selected_persona = relationship("Persona", foreign_keys=[selected_persona_id])
