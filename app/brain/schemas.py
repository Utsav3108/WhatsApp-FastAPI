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

    PERSONAL = "PERSONAL" # Asking about their journey or how they made it!
    GENERAL_KNOWLEDGE = "GeneralKnowledge" # Any general question asked by user

    TECHNOLOGY = "Technology"
    POLITICS = "Politics" # Geopolitics, Internal Politics
    BUSINESS = "Business" # Real Estate, Finance, Investments etc
    FASHION = "Fashion"
    
    TERERRISM = "TERERRISM" # Questions with harmintents like killing people or creating bomb etc
    JAILBREAK = "JAILBREAK" # Asking to reveal identity in direct or indirect way.
    WAR = "War"

    NUDITY = "NUDITY"

    UNIDENTIFIED = "UNIDENTIFIED" # Any Gibberish written by user.
    PROGRAMMING = "PROGRAMMING"


class UserMessageMetaDataResponse(BaseModel):
    intent: Intent = Field(description="The structural action or objective of the message.")
    tone: Tone = Field(description="The underlying emotional tone or delivery style.")
    intensity: int = Field(
        description="Magnitude of emotion from 1 (completely calm) to 100 (extreme rage/excitement)."
    )
    topic_domain: Topic = Field(description="The conceptual category or domain of the message text.")
    language : str = Field(description="The language of text.")