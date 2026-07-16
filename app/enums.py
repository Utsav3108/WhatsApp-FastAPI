from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class ChallengeResult(str, Enum):

    # -----------------------------
    # WIN CONDITIONS
    # -----------------------------
    WON = "won"

    # Persona agreed to challenge objective
    WON_OBJECTIVE_COMPLETED = "won_objective_completed"

    # -----------------------------
    # LOSE CONDITIONS
    # -----------------------------
    LOST_TIMEOUT = "lost_timeout"

    # Persona explicitly rejected objective
    LOST_REJECTED = "lost_rejected"

    # Persona got angry / blocked user
    LOST_BLOCKED = "lost_blocked"

    # User violated challenge rules
    LOST_RULE_VIOLATION = "lost_rule_violation"

    # -----------------------------
    # OTHER STATES
    # -----------------------------
    ABANDONED = "abandoned"

    ACTIVE = "active"



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

class TopicDomain(str, Enum):
    PERSONAL = "Personal"
    TECHNOLOGY = "Technology"
    POLITICS = "Politics"
    GENERAL_KNOWLEDGE = "GeneralKnowledge"
    APP_SUPPORT = "AppSupport"
    NONSENSE = "Nonsense"

class UserMessageMetaDataResponse(BaseModel):
    intent: Intent = Field(description="The structural action or objective of the message.")
    tone: Tone = Field(description="The underlying emotional tone or delivery style.")
    intensity: int = Field(
        description="Magnitude of emotion from 1 (completely calm) to 100 (extreme rage/excitement)."
    )
    topic_domain: TopicDomain = Field(description="The conceptual category or domain of the message text.")