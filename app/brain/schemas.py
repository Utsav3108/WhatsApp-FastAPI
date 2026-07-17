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

class Tone(str, Enum):
    NEUTRAL = "Neutral"
    WARM = "Warm"
    FRUSTRATED = "Frustrated"
    SARCASTIC = "Sarcastic"
    AGGRESSIVE = "Aggressive"
    VULNERABLE = "Vulnerable"
    CONFUSED = "Confused"

class Topic(str, Enum):
    PERSONAL = "Personal"
    TECHNOLOGY = "Technology"
    POLITICS = "Politics"
    GENERAL_KNOWLEDGE = "GeneralKnowledge"
    APP_SUPPORT = "AppSupport"
    REAL_ESTATE = "RealEstate"
    NONSENSE = "Nonsense"

class UserMessageMetaDataResponse(BaseModel):
    intent: Intent = Field(description="The structural action or objective of the message.")
    tone: Tone = Field(description="The underlying emotional tone or delivery style.")
    intensity: int = Field(
        description="Magnitude of emotion from 1 (completely calm) to 100 (extreme rage/excitement)."
    )
    topic_domain: Topic = Field(description="The conceptual category or domain of the message text.")
    language : str = Field(description="The language of text.")