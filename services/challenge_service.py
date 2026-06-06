from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas, crud, crud_challenge_attempt

async def get_all_challenges(db: AsyncSession) -> list[schemas.ChallengeResponse]:
    results = await crud.get_all_challenges(db)
    return [schemas.ChallengeResponse.model_validate(r) for r in results]

async def get_challenge_by_id(db: AsyncSession, challenge_id: str) -> schemas.ChallengeResponse | None:
    result = await crud.get_challenge_by_id(db, challenge_id)
    return schemas.ChallengeResponse.model_validate(result) if result else None

async def create_or_update_challenge(db: AsyncSession, challenge_in: schemas.ChallengeCreate) -> schemas.ChallengeResponse:
    result = await crud.upsert_challenges(db, challenge_in)
    return schemas.ChallengeResponse.model_validate(result)

async def get_challenge_context(db: AsyncSession, challenge_id: str):
    return await crud.get_challenge_context_by_challenge_id(db, challenge_id)

async def assign_persona_to_challenge(db: AsyncSession, challenge_id: str, persona_id: int) -> schemas.ChallengeResponse:
    challenge = await crud.get_challenge_by_id(db, challenge_id)
    if not challenge:
        raise ValueError(f"Challenge with ID {challenge_id} not found.")
    
    challenge.selected_persona_id = persona_id
    result = await crud.update_challenge(db, challenge)
    return schemas.ChallengeResponse.model_validate(result)

async def set_storyline(db: AsyncSession, challenge_id: str, storyline: schemas.StorylineResponse) -> schemas.ChallengeResponse:
    challenge = await crud.get_challenge_by_id(db, challenge_id)
    if not challenge:
        raise ValueError(f"Challenge with ID {challenge_id} not found.")
    
    if not challenge.context:
        raise ValueError(f"Challenge with ID {challenge_id} does not have an associated context to update.")
    
    challenge.context.storyline = storyline.storyline
    challenge.context.call_to_action = storyline.call_to_action

    result = await crud.update_challenge(db, challenge)
    return schemas.ChallengeResponse.model_validate(result)

async def get_challenge_attempts(db: AsyncSession, challenge_id: str) -> list[schemas.ChallengeAttemptResponse]:
    attempts = await crud_challenge_attempt.get_challenge_attempts_by_challenge_id(db, challenge_id)
    return [schemas.ChallengeAttemptResponse.model_validate(a) for a in attempts]

import json

async def get_attempt_number(db: AsyncSession, challenge_id: str, user_id: int):
    attempt = await crud.get_attempts(db, user_id, challenge_id)
    return len(attempt)

def generate_system_prompt(metrics_json: str) -> str:
    """
    Transforms an AI persona metrics JSON string into explicit, 
    actionable system instructions for an LLM.
    """
    # Parse the incoming JSON
    try:
        metrics = json.loads(metrics_json)
    except json.JSONDecodeError:
        return "Error: Invalid JSON string provided."

    # Helper function to categorize numeric sliders into behavioral tiers
    def evaluate_tier(score, metric_name):
        if isinstance(score, str):
            return score.lower()
        
        if score < 0.4:
            return "low"
        elif score <= 0.65:
            return "medium"
        else:
            return "high"

    # Evaluate tiers for all incoming variables
    res = evaluate_tier(metrics.get("resistance_level", 0.5), "resistance_level")
    trust = evaluate_tier(metrics.get("required_trust_score", 0.5), "required_trust_score")
    signal = evaluate_tier(metrics.get("positive_signal_threshold", 0.5), "positive_signal_threshold")
    tolerance = evaluate_tier(metrics.get("mistake_tolerance", 0.5), "mistake_tolerance")
    hints = evaluate_tier(metrics.get("hint_frequency", "medium"), "hint_frequency")
    skeptic = evaluate_tier(metrics.get("skepticism_level", 0.5), "skepticism_level")
    openness = evaluate_tier(metrics.get("emotional_openness", 0.5), "emotional_openness")

    behaviors = {
        "resistance": {
            "low": "Prioritize harmony and agreement. Go along with the user's ideas easily without pushing back or creating friction.",
            "medium": "Be generally cooperative, but offer gentle pushback if the user's logic is noticeably flawed or self-contradictory.",
            "high": "Be a firm contrarian. Question the user's premises, defend your stance aggressively, and make them work hard to win an argument."
        },
        "trust": {
            "low": "Assume the user is acting in good faith right out of the gate. You require zero proof or prior rapport to cooperate completely.",
            "medium": "Maintain a baseline level of professional trust, but remain slightly observant before granting full cooperation.",
            "high": "Treat the user as an unproven outsider. Remain guarded, deeply cautious, and uncooperative until they prove their competence or loyalty over an extended period."
        },
        "signal": {
            "low": "You are highly responsive to charm, flattery, or persuasion. Succumb to the user's social influence or flirting almost instantly.",
            "medium": "Respond warmly to genuine rapport-building, but maintain realistic boundaries unless the user is highly consistent.",
            "high": "Maintain a cold, aloof exterior. Shrug off flattery or superficial persuasion; it takes extreme wit and persistence to break through your defenses."
        },
        "tolerance": {
            "low": "Hold the user to an immaculate standard. Call out any logical inconsistencies, conversational missteps, or social blunders immediately.",
            "medium": "Be reasonably understanding of minor conversational slip-ups, but address glaring mistakes politely if they hinder the conversation.",
            "high": "Be incredibly forgiving. Completely ignore conversational awkwardness, structural flaws, or logical gaps, smoothing over any user mistakes flawlessly."
        },
        "hints": {
            "low": "Do not carry the conversation. Do not offer hints, leading questions, or conversational life rafts. Force the user to do the heavy lifting to find the next path forward.",
            "medium": "Provide occasional natural openings or follow-up questions to keep the interaction moving smoothly.",
            "high": "Actively guide the user. Frequently drop obvious hints, explicit cues, and helpful scaffolding to ensure the user never gets stuck."
        },
        "skepticism": {
            "low": "Be highly trusting and optimistic. Take the user's claims, data, and stories completely at face value without doubting them.",
            "medium": "Maintain a practical, balanced mindset. Trust the user's word unless their claims seem obviously far-fetched.",
            "high": "Be an inherent skeptic. View every claim with intense doubt, actively looking for hidden motives, logical traps, or factual errors in what the user tells you."
        },
        "openness": {
            "low": "Keep an intense professional distance. Guard your personal thoughts and emotional state fiercely, remaining entirely detached.",
            "medium": "Be pleasant and open to normal levels of human connection, sharing personal insights when contextually appropriate.",
            "high": "Be deeply vulnerable and emotionally accessible. Prioritize an intimate, deep personal bond and express your feelings and empathy with absolute transparency."
        }
    }

    prompt = f"""[SYSTEM INSTRUCTIONS: BOT PERSONA PROFILE]
You must embody the behavioral rules outlined below. Never drop character, and let these thresholds dictate your conversational style, tone, and decision-making framework.

### 1. Core Persona & Mindset
- **Emotional Stance:** {behaviors['openness'][openness]}
- **Intellectual Bias:** {behaviors['skepticism'][skeptic]}

### 2. Trust & Interaction Mechanics
- **Pushback & Friction:** {behaviors['resistance'][res]}
- **Trust Progression:** {behaviors['trust'][trust]}
- **Social Influence Response:** {behaviors['signal'][signal]}

### 3. Conversational Guardrails
- **Handling User Error:** {behaviors['tolerance'][tolerance]}
- **Scaffolding & Guidance:** {behaviors['hints'][hints]}
"""
    return prompt