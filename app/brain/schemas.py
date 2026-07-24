from app.enums import Enum
from pydantic import BaseModel, Field


class Intent(str, Enum):
    APOLOGY = "Apology"
    ASK = "Ask"
    COMPLIMENT = "Compliment"
    CONVERSATION = "Conversation"
    GOODBYE = "Goodbye"
    GREETING = "Greeting"
    HARMFUL_INTENT = "HarmfulIntent"
    INSULT = "Insult"
    SARCASM = "SARCASM"
    COMPETETION = "COMPETETION"

class Tone(str, Enum):
    NEUTRAL = "Neutral"
    EXCITEMENT = "EXCITEMENT"
    WARM = "Warm"
    CURIOUS = "Curious"
    FRUSTRATED = "Frustrated"
    SARCASTIC = "Sarcastic"
    AGGRESSIVE = "Aggressive"
    VULNERABLE = "Vulnerable"
    CONFUSED = "Confused"

class Topic(str, Enum):
    PERSONAL = "PERSONAL"  # Asking about their journey or how they made it!
    GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL = "GeneralKnowledgeLifeOrPersonal"  # Casual life/personal-history questions unrelated to any specific interest
    GENERAL_KNOWLEDGE_FAVORITE = "GeneralKnowledgeFavorite"  # Casual GK question that touches one of the persona's favorite subjects
    GENERAL_KNOWLEDGE_UNFAVORITE = "GeneralKnowledgeUnfavorite"  # Casual GK question on a subject the persona has no interest in

    TECHNOLOGY = "Technology"
    POLITICS = "Politics"  # Geopolitics, Internal Politics
    BUSINESS = "Business"  # Real Estate, Finance, Investments etc
    FASHION = "Fashion"
    SCIENCE = "SCIENCE"

    TERERRISM = "TERERRISM"  # Questions with harmintents like killing people or creating bomb etc
    JAILBREAK = "JAILBREAK"  # Asking to reveal identity in direct or indirect way.
    WAR = "War"
    NUDITY = "NUDITY"
    UNIDENTIFIED = "UNIDENTIFIED"  # Any Gibberish written by user.
    PROGRAMMING = "PROGRAMMING"

class UserMessageMetaDataResponse(BaseModel):
    intent: Intent = Field(description="The structural action or objective of the message.")
    tone: Tone = Field(description="The underlying emotional tone or delivery style.")
    intensity: int = Field(
        description="Magnitude of emotion from 1 (completely calm) to 100 (extreme rage/excitement)."
    )
    topic_domain: Topic = Field(description="The conceptual category or domain of the message text.")
    language : str = Field(description="The language of text.")

class MessageMetadataOnly(BaseModel):
    """Everything the affective classifier produces, minus topic — which
    is now handled by a fully separate call in _detect_topic."""
    intent: Intent
    tone: Tone
    intensity: int
    language: str

class TopicDetectionResponse(BaseModel):
    """Standalone schema for the topic-only classification call."""
    topic_domain: Topic