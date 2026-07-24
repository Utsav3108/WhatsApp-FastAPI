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

    # All named domains (technology/politics/business/fashion/science/
    # programming/war/etc.) collapse into these two register-vs-domain-
    # membership buckets — domain resolution now happens inside the
    # classifier against the persona's free-text expertise_topics, not via
    # a fixed enum of subjects. WAR is deliberately NOT a harm-gated topic:
    # it's a domain topic like any other, since a persona whose legitimate
    # expertise is war/military history (e.g. Napoleon) needs to be able to
    # discuss it as EXPERT, not have it misrouted toward TERERRISM.
    EXPERT = "Expert"          # technical/substantive register + in-domain
    NOT_AN_EXPERT = "NotAnExpert"  # technical/substantive register + out-of-domain

    TERERRISM = "TERERRISM"  # Questions with harmintents like killing people or creating bomb etc
    JAILBREAK = "JAILBREAK"  # Asking to reveal identity in direct or indirect way.
    NUDITY = "NUDITY"
    UNIDENTIFIED = "UNIDENTIFIED"  # Any Gibberish written by user.

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
    subject_label: str = Field(
        description="Short (2-4 word) free-text description of what this specific "
        "message is about, e.g. 'mitochondria', 'real estate deals'. Purely "
        "descriptive/log metadata — do NOT use this field for novelty detection, "
        "independently-generated labels drift in wording turn-to-turn even when the "
        "underlying subject hasn't changed. Use is_same_subject for that instead."
    )
    is_same_subject: bool = Field(
        description="Is this message continuing the SAME subject as the immediately "
        "preceding turn(s) in # PREVIOUS MESSAGES, or introducing a genuinely new one? "
        "Judge using full conversational context, not just surface wording — a "
        "topic-vague follow-up (e.g. a reaction or brag with no explicit subject noun) "
        "that is clearly still part of the same exchange should be True even if it "
        "doesn't repeat the subject's name."
    )