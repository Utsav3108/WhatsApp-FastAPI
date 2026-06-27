

import datetime
import json
from typing import Any, List, Optional, Union, Annotated
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator

from app import enums

class IdentityModel(BaseModel):
    nickname: Optional[str] = ""
    profession: Optional[str] = ""
    age: Optional[str] = ""
    nationality: Optional[str] = ""
    gender: Optional[str] = ""
    intro: Optional[str] = ""

class PersonalitySlidersModel(BaseModel):
    confidence: Optional[int] = 5
    humor: Optional[int] = 5
    warmth: Optional[int] = 5
    curiosity: Optional[int] = 5
    competitiveness: Optional[int] = 5
    patience: Optional[int] = 5
    emotionality: Optional[int] = 5
    assertiveness: Optional[int] = 5
    intelligence: Optional[int] = 5
    playfulness: Optional[int] = 5

class SpeechStyleModel(BaseModel):
    tone: Optional[str] = "Casual"
    modifiers: Optional[List[str]] = []
    custom: Optional[str] = ""

class EmotionalProfileModel(BaseModel):
    traits: Optional[List[str]] = []
    custom: Optional[str] = ""

class HumorModel(BaseModel):
    types: Optional[List[str]] = []
    custom: Optional[str] = ""

class InterestsExpertiseModel(BaseModel):
    interests: Optional[List[str]] = []
    expertise: Optional[List[str]] = []

class LikesDislikesModel(BaseModel):
    likes: Optional[List[str]] = []
    dislikes: Optional[List[str]] = []

class RelationshipStyleModel(BaseModel):
    treat_user_as: Optional[str] = "Friend"
    behaviors: Optional[List[str]] = []

class ResponseRulesModel(BaseModel):
    guidelines: Optional[List[str]] = []
    custom: Optional[str] = ""

class DialogueExampleModel(BaseModel):
    user: Optional[str] = ""
    persona: Optional[str] = ""

class StructuredTraits(BaseModel):
    identity: Optional[IdentityModel] = None
    personality_sliders: Optional[PersonalitySlidersModel] = None
    custom_traits: Optional[List[str]] = []
    values: Optional[List[str]] = []
    speech_style: Optional[SpeechStyleModel] = None
    emotional_profile: Optional[EmotionalProfileModel] = None
    humor: Optional[HumorModel] = None
    interests_expertise: Optional[InterestsExpertiseModel] = None
    likes_dislikes: Optional[LikesDislikesModel] = None
    backstory: Optional[str] = ""
    relationship_style: Optional[RelationshipStyleModel] = None
    response_rules: Optional[ResponseRulesModel] = None
    example_dialogues: Optional[List[DialogueExampleModel]] = []

def parse_traits(v: Any) -> Any:
    if isinstance(v, str):
        v_stripped = v.strip()
        if v_stripped.startswith('{') or v_stripped.startswith('['):
            try:
                return json.loads(v)
            except Exception:
                pass
    return v

TraitsType = Annotated[Union[StructuredTraits, str], BeforeValidator(parse_traits)]

class PersonaCreate(BaseModel):
    name: str
    desc: str
    traits: TraitsType
    image_url: str
    is_human: Optional[bool] = False
    category: Optional[str] = "Custom Creator"
    email: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None
    settings: Optional[dict] = None

class PersonaResponse(BaseModel):
    id: int
    name: str
    desc: str
    traits: TraitsType
    image_url: str
    is_human: bool = False
    category: str = "Custom Creator"
    email: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None
    settings: Optional[dict] = None

    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    role: Optional[str] = None
    bio: Optional[str] = None
    settings: Optional[dict] = None

class ProfileAttemptLogItem(BaseModel):
    challenge_id: str
    challenge_title: str
    persona_name: str
    won: bool
    created_at: datetime.datetime
    challenge_session_id: int
    persona_id: int

class ProfileStats(BaseModel):
    total_challenges_attempted: int
    success_rate_percentage: float
    total_practice_sessions: int

class UserProfileResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    bio: Optional[str] = None
    image_url: str
    settings: Optional[dict] = None
    stats: ProfileStats
    attempts_log: List[ProfileAttemptLogItem]

class GoogleLoginRequest(BaseModel):
    id_token: str


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
    storyline: Optional[str] = None
    call_to_action: Optional[str] = None

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

    for_user: bool = True # New field to indicate if the challenge is for users or for personas
    first_message_from_persona: bool = False
    selected_persona_id: Optional[int] = None  # New field for selected persona ID
    created_at: Optional[datetime.datetime] = None

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
    attempt_session_id: Optional[int] = None  # New field to link to a specific attempt session if fetching history.

class ChallengeSetupResponse(BaseModel):
    message: str
    challenge_session_id: Optional[int] = None
    intro: Optional[StorylineResponse] = None
    status: Optional[enums.ChallengeResult] = None
    total_duration_minutes: Optional[int] = None
    elapsed_seconds: int = 0


class ConversationRequest(BaseModel):
    """Discriminated by which optional fields are present:
    - sender_id + receiver_id  → persona-to-persona chat
    - challenge_session_id      → ongoing challenge session
    - attempt_session_id        → past completed challenge (treated as challenge_session_id)
    """
    sender_id: Optional[int] = None
    receiver_id: Optional[int] = None
    challenge_session_id: Optional[int] = None
    attempt_session_id: Optional[int] = None


class PaginatedMessagesResponse(BaseModel):
    messages: List[MessageResponse]
    page: int
    page_size: int
    total_count: int
    total_pages: int
    has_more: bool


class ChallengeSessionResponse(BaseModel):
    id: int
    user_id: int
    challenge_id: str
    persona_id: int
    status: str
    result_reason: Optional[str] = None
    storyline: Optional[str] = None
    call_to_action: Optional[str] = None
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True
    

class ChallengeCompletion(BaseModel):
    reason: Optional[str] = None  
    challenge_status: enums.ChallengeResult
    challenge_session_id: int
    user_id: int
    challenge_id: str

class ChallengeCompletionResponse(BaseModel):
    message : str
    challenge_status : str
    result_reason: Optional[str] = None

    class Config:
        from_attributes = True

# Storyline schemas
class StorylineRequest(BaseModel):
    challenge_id: str

class StorylineResponse(BaseModel):
    storyline: str = Field(description="The intro story with dynamic pauses like [pause: 1.0]")
    call_to_action: Optional[str] = Field(description="A clear, short instruction telling the user what to do next")
    end_goal: Optional[str] = Field(default=None, description="The ultimate objective or success condition of this challenge")


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
    difficulty: Optional[ChallengeDifficulty] = None
    created_at: datetime.datetime
    challenge_session_id: int

    class Config:
        from_attributes = True

from app.enums import ChallengeResult

class EvaluationResponse(BaseModel):
    status: ChallengeResult = Field(
        description="The current evaluation state of the challenge based on the conversation."
    )
    reasoning: str = Field(
        description="A brief, 1-2 sentence explanation of why this status was selected based on the latest context and messages."
    )

class ChallengeDashboardResponse(BaseModel):
    daily_challenge: Optional[ChallengeResponse] = None
    trending_challenges: List[ChallengeResponse]
    recommended_challenges: List[ChallengeResponse]
    recently_added_challenges: List[ChallengeResponse]

class CategoryBase(BaseModel):
    name: str
    keywords: Optional[List[str]] = None
    icon: Optional[str] = None
    gradient_colors: Optional[List[str]] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryResponse(CategoryBase):
    id: int

    class Config:
        from_attributes = True

class AIContentReportCreate(BaseModel):
    message_id: int
    conversation_id: Optional[int] = None
    persona_id: int
    user_prompt: Optional[str] = None
    ai_response: str
    reason: str
    description: Optional[str] = None

class AIContentReportResponse(AIContentReportCreate):
    id: int
    timestamp: datetime.datetime

    class Config:
        from_attributes = True