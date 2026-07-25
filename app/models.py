import uuid
import json
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, JSON, Enum, UniqueConstraint
from sqlalchemy.types import TypeDecorator, TEXT
from app.database import Base
from sqlalchemy import DateTime
from datetime import datetime, timezone
import enum

from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

class CompatibleJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB)
        return dialect.type_descriptor(JSON)

class SafeJSON(TypeDecorator):
    impl = TEXT
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB)
        return dialect.type_descriptor(TEXT)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        elif hasattr(value, "dict"):
            value = value.dict()
        
        if isinstance(value, str):
            v_stripped = value.strip()
            if v_stripped.startswith('{') or v_stripped.startswith('['):
                try:
                    value = json.loads(v_stripped)
                except Exception:
                    pass

        if dialect.name == 'postgresql':
            return value

        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == 'postgresql':
            return value
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value


# ChallengeContext table
from sqlalchemy.orm import relationship




# ChallengeAttempt table
class ChallengeAttempt(Base):
    __tablename__ = "challenge_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_session_id = Column(Integer, ForeignKey("challenge_sessions.id"), nullable=False, index=True)
    challenge_id = Column(String, ForeignKey("challenges.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)  # Now references Persona
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    role_mode = Column(String)
    won = Column(Boolean, nullable=False)
    time_taken_seconds = Column(Integer)
    attempt_number = Column(Integer)
    difficulty = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    challenge_session = relationship("ChallengeSession", back_populates="attempts")
    user = relationship("Persona", foreign_keys=[user_id])
    challenge = relationship("Challenge")
    persona = relationship("Persona", foreign_keys=[persona_id])

class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    desc = Column(String)
    traits = Column(SafeJSON)
    image_url = Column(String, default="")
    is_human = Column(Boolean, nullable=False, server_default="false", default=False)
    category = Column(String, default="Custom Creator", nullable=True)
    email = Column(String, nullable=True, index=True)
    role = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    settings = Column(SafeJSON, nullable=True)
    is_admin = Column(Boolean, nullable=False, server_default="false", default=False)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)

class PersonaSessionModel(Base):
    """
    Persisted Brain/emotion-engine state for one (ai_persona, human_persona)
    pair — the DB-backed counterpart to the in-memory
    app.persona.persona_session.PersonaSession class (deliberately named
    differently to avoid an import collision in any file that needs both).
    Regular persona chat only; challenges don't use this yet (see
    messages.persona_session_id below).
    """
    __tablename__ = "persona_sessions"

    id = Column(Integer, primary_key=True, index=True)

    ai_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    human_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    # Deliberately no unique constraint on (ai_persona_id, human_persona_id)
    # — multiple concurrent sessions per pair (forks) are a supported case.

    arousal = Column(Float, nullable=False)
    patience = Column(Float, nullable=False)
    mood = Column(Float, nullable=False, default=0)
    rapport = Column(Float, nullable=False, default=0)
    curiosity = Column(Float, nullable=False, default=0)

    last_subject = Column(String, nullable=True)
    topic_repeat_streak = Column(Integer, nullable=False, default=0)
    turn_count = Column(Integer, nullable=False, default=0)

    violation_count = Column(Integer, nullable=False, default=0)
    is_blocked = Column(Boolean, nullable=False, default=False)
    block_reason = Column(String, nullable=True)

    blocked_until = Column(DateTime(timezone=True), nullable=True)
    # NULL = not blocked. Non-null = blocked until this moment (auto-
    # expiring — see BLOCK_DURATION_HOURS in persona_session.py). is_blocked
    # above is kept as a real, separately-stored cached/convenience flag,
    # not fully derived from this column at the DB level.

    last_emotional_update_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Bumped ONLY when update()/register_violation() actually mutate state
    # this turn — NOT on the hard-gate short-circuit or other no-mutation
    # early returns. This is the anchor decay math reads elapsed time
    # against; deliberately separate from updated_at (fork-recency ordering
    # only, bumped on every save() call regardless).

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # onupdate=func.now() is what makes "most-recent-active fork" selection
    # work without extra application-level bookkeeping — bumped on every
    # save() call.

    ai_persona = relationship("Persona", foreign_keys=[ai_persona_id])
    human_persona = relationship("Persona", foreign_keys=[human_persona_id])

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("personas.id"), index=True)
    receiver_id = Column(Integer, ForeignKey("personas.id"), index=True)
    text = Column(String)
    is_user = Column(Boolean, nullable=False, server_default="false", default=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    image_object_name = Column(String, nullable=True)

    challenge_session_id = Column(
        Integer,
        ForeignKey("challenge_sessions.id"),
        nullable=True,
        index=True
    )

    persona_session_id = Column(
        Integer,
        ForeignKey("persona_sessions.id"),
        nullable=True,
        index=True
    )
    # Mirrors challenge_session_id above. A regular-chat message should have
    # this set; a challenge message currently should NOT (until a future
    # task wires Brain/PersonaSession into challenges too, at which point
    # this and challenge_session_id will need to coexist on the same row).
    # Deliberately no CHECK constraint enforcing mutual exclusivity with
    # challenge_session_id — that assumption won't hold once challenges
    # adopt Brain as well.



class ChallengeContext(Base):
    __tablename__ = "challenge_contexts"

    id = Column(Integer, primary_key=True, index=True)
    challenge_id = Column(String, ForeignKey("challenges.id"), unique=True)
    setting = Column(String)
    environment = Column(CompatibleJSON, nullable=True)  # Optional, JSON type
    goal = Column(String)
    stakes = Column(String)
    platform = Column(String)
    challenge = relationship("Challenge", back_populates="context")
    storyline = Column(String, nullable=True)
    call_to_action = Column(String, nullable=True)



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
    categories = Column(CompatibleJSON, nullable=True)
    suggested_personas = Column(CompatibleJSON, nullable=True)
    difficulty = Column(
        Enum(
            ChallengeDifficulty,
            name="challenge_difficulty"
        ),
        nullable=True
    )
    difficulty_settings = Column(CompatibleJSON, nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=True)
    challenge_rules = Column(CompatibleJSON, nullable=True)
    image_url = Column(String, nullable=True)
    for_user = Column(Boolean, nullable=False, server_default="true", default=True)
    first_message_from_persona = Column(Boolean, nullable=False, server_default="false", default=False)
    context = relationship("ChallengeContext", uselist=False, back_populates="challenge", cascade="all, delete-orphan")

    selected_persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)  # New field for selected persona
    selected_persona = relationship("Persona", foreign_keys=[selected_persona_id])
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

class ChallengeSession(Base):

    __tablename__ = "challenge_sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("personas.id"),
        nullable=False,
        index=True
    )

    challenge_id = Column(
        String,
        ForeignKey("challenges.id"),
        nullable=False,
        index=True
    )

    persona_id = Column(
        Integer,
        ForeignKey("personas.id"),
        nullable=False,
        index=True
    )

    status = Column(
        String,
        nullable=False,
        default="active"
    )

    result_reason = Column(String, nullable=True)

    storyline = Column(Text, nullable=True)

    call_to_action = Column(String, nullable=True)

    started_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    completed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    elapsed_seconds = Column(Integer, default=0, nullable=False)
    last_resumed_at = Column(DateTime(timezone=True), nullable=True)

    attempts = relationship("ChallengeAttempt", back_populates="challenge_session", cascade="all, delete-orphan")

    challenge = relationship("Challenge")

    persona = relationship(
        "Persona",
        foreign_keys=[persona_id]
    )

    user = relationship(
        "Persona",
        foreign_keys=[user_id]
    )

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    keywords = Column(CompatibleJSON, nullable=True)
    icon = Column(String, nullable=True)
    gradient_colors = Column(CompatibleJSON, nullable=True)

class AIContentReport(Base):
    __tablename__ = "ai_content_reports"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    conversation_id = Column(Integer, ForeignKey("challenge_sessions.id"), nullable=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    user_prompt = Column(String, nullable=True)
    ai_response = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    description = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    message = relationship("Message")
    persona = relationship("Persona", foreign_keys=[persona_id])
    conversation = relationship("ChallengeSession", foreign_keys=[conversation_id])

class AdminAuditLog(Base):
    """
    Attribution trail for admin-only actions (e.g. persona-session
    reset-block, persona soft-delete). target_id is a plain string (not an
    FK) since target_type discriminates which table it actually points at
    (persona_session vs persona) — avoids two nullable FK columns for one
    logical reference.
    """
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    action = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False, index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    admin = relationship("Persona", foreign_keys=[admin_id])