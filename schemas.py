

import datetime

from pydantic import BaseModel, ConfigDict
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app import enums

class PersonaCreate(BaseModel):
    name: str
    desc: str
    traits: str
    image_url: str

class PersonaResponse(BaseModel):
    id: int
    name: str
    desc: str
    image_url: str

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    sender_id: int
    receiver_id: int
    text: str
    image_object_name: Optional[str] = None
    challenge_session_id: Optional[int] = None

class MessageResponse(MessageCreate):
    id: int

    class Config:
        from_attributes = True




# Challenge schemas
from typing import Dict, Optional, Any
from enum import Enum

class ChallengeContextBase(BaseModel):
    setting: str
    environment: Optional[Any] = None  # JSON field, optional
    goal: str
    stakes: str
    platform: str

# Enum for challenge difficulty
class ChallengeDifficulty(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advance = "advance"

class ChallengeContextCreate(ChallengeContextBase):
    pass

class ChallengeContextResponse(ChallengeContextBase):
    id: int
    challenge_id: str

    class Config:
        from_attributes = True


class ChallengeBase(BaseModel):

    model_config = ConfigDict(from_attributes=True)


    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    categories: Optional[list[str]] = None
    suggested_personas: Optional[list[int]] = None
    difficulty: Optional[ChallengeDifficulty] = None
    difficulty_settings: Optional[dict] = None
    estimated_duration_minutes: Optional[int] = None
    challenge_rules: Optional[dict] = None
    image_url: Optional[str] = None
    selected_persona_id: Optional[int] = None  # New field for selected persona ID

class ChallengeCreate(ChallengeBase):
    id: str
    context: ChallengeContextCreate


class ChallengeResponse(ChallengeBase):
    id: str
    context: Optional[ChallengeContextResponse]

    class Config:
        from_attributes = True

class ChallengeSetup(BaseModel):
    challenge_id: str
    persona_id: Optional[int] = None 
    user_id: int

class ChallengeSetupResponse(BaseModel):
    message: str
    challenge_session_id: Optional[int] = None
    intro: Optional[StorylineResponse] = None
    status: Optional[enums.ChallengeResult] = None
    total_duration_minutes: Optional[int] = None
    

class ChallengeCompletion(BaseModel):
    reason: Optional[str] = None  
    challenge_status: enums.ChallengeResult
    challenge_session_id: int
    user_id: int
    challenge_id: int

class ChallengeCompletionResponse(BaseModel):
    message : str
    result_reason: Optional[str] = None

    class Config:
        from_attributes = True

# Storyline schemas
class StorylineRequest(BaseModel):
    challenge_id: str

class StorylineResponse(BaseModel):
    storyline: str = Field(description="The intro story with dynamic pauses like [pause: 1.0]")
    call_to_action: str = Field(description="A clear, short instruction telling the user what to do next")


from uuid import UUID

class ChallengeAttemptResponse(BaseModel):
    id: UUID
    challenge_id: str
    user_id: int
    persona_id: int
    role_mode: str | None = None
    won: bool
    time_taken_seconds: int | None = None
    attempt_number: int | None = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True