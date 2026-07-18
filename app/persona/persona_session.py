# app/brain/persona_session.py
from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from app.brain.emotion_engine import EmotionEngine, clamp
from typing import Dict, List, Optional
from app.brain.context import BrainContext
from app.brain.brain_component import BrainComponent


class PersonaSession(BrainComponent):
    def __init__(self, name: str, traits: Dict[str, float], expertise_topics: Optional[List[Topic]] = None):

        self.summary = ""

        self.persona = name

        self.threat_sensitivity = traits.get('threat_sensitivity', 50.0)
        self.self_regulation = traits.get('self_regulation', 50.0)
        self.novelty_drive = traits.get('novelty_drive', 50.0)
        self.baseline_security = traits.get('baseline_security', 50.0)
        self.empathic_resonance = traits.get('empathic_resonance', 50.0)

        self.expertise_topics = expertise_topics if expertise_topics is not None else [Topic.GENERAL_KNOWLEDGE]

        self.arousal = max(0.0, 30.0 - (self.baseline_security / 4.0))
        self.patience = min(100.0, 40.0 + (self.self_regulation / 2.0))
        self.mood = 0.0
        self.rapport = 0.0
        self.curiosity = 0.0

        self.last_topic: Optional[Topic] = None
        self.topic_repeat_streak = 0
        self.greeting_streak = 0
        self.turn_count = 0
        self.is_first_turn = True  # read by compile_prompt before turn_count increments

        self.is_blocked = False
        self.BLOCK_THRESHOLD = 100

    def _apply(self, deltas: dict):
        if "arousal" in deltas:
            self.arousal = clamp(self.arousal + deltas["arousal"], 0.0, 100.0)
        if "patience" in deltas:
            self.patience = clamp(self.patience + deltas["patience"], 0.0, 100.0)
        if "mood" in deltas:
            self.mood = clamp(self.mood + deltas["mood"], -100.0, 100.0)
        if "rapport" in deltas:
            self.rapport = clamp(self.rapport + deltas["rapport"], 0.0, 100.0)

    def update(self, context: BrainContext):
        intent = context.metadata.intent
        tone = context.metadata.tone
        intensity = float(context.metadata.intensity)
        topic = context.metadata.topic_domain

        self.is_first_turn = (self.turn_count == 0)
        is_hostile_turn = intent in [Intent.INSULT, Intent.HARMFUL_INTENT] and tone in [Tone.AGGRESSIVE]

        # --- 1. STATE MATH ENGINE ---
        if intent == Intent.COMPLIMENT or tone == Tone.WARM:
            self._apply(EmotionEngine.compliment_delta(intensity))

        elif is_hostile_turn:
            self._apply(EmotionEngine.hostility_delta(self.threat_sensitivity, self.self_regulation, tone, intensity))

        elif intent == Intent.APOLOGY:
            self._apply(EmotionEngine.apology_delta(self.empathic_resonance, self.baseline_security, self.arousal, intensity))

        elif intent == Intent.GREETING:
            # first-ever greeting of the session is free — handled in compile_prompt
            if not self.is_first_turn:
                self._apply(EmotionEngine.greeting_delta(self.self_regulation, self.threat_sensitivity, self.greeting_streak))

        elif intent in [Intent.CONVERSATION, Intent.ASK]:
            self._apply(EmotionEngine.conversation_drain(self.self_regulation, self.rapport, intensity))

        # GOODBYE: intentional no-op.

        self.greeting_streak = self.greeting_streak + 1 if intent == Intent.GREETING else 0

        # --- 2. NOVELTY / CURIOSITY ENGINE ---
        is_new_topic = topic != self.last_topic
        in_expertise = topic in self.expertise_topics

        curiosity_delta = EmotionEngine.curiosity_delta(
            novelty_drive=self.novelty_drive,
            intensity=intensity,
            in_expertise=in_expertise,
            is_new_topic=is_new_topic,
            tone=tone,
            topic_repeat_streak=self.topic_repeat_streak,
            is_hostile_turn=is_hostile_turn,
        )
        self.curiosity = clamp(self.curiosity + curiosity_delta, 0.0, 100.0)

        self.topic_repeat_streak = 0 if is_new_topic else self.topic_repeat_streak + 1
        self.last_topic = topic
        self.turn_count += 1

    def compile_prompt(self, context: BrainContext) -> str:
        if self.is_blocked:
            return f"[{self.persona} is currently completely unresponsive. Refuse to engage entirely.]"

        if self.arousal >= self.BLOCK_THRESHOLD:
            self.is_blocked = True
            return f"[{self.persona} is furious. Abruptly shut down the conversation and refuse to answer.]"

        intent = context.metadata.intent
        topic = context.metadata.topic_domain

        # Literal first message of the session, and it's a greeting: skip the
        # whole personality stack, just say hello back in kind.
        if intent == Intent.GREETING and self.is_first_turn:
            return (
                "CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
                "- Just greet the user back, matching their tone and energy. One short line, no elaboration."
            )

        if self.arousal >= 70:
            arousal_str = "Highly agitated and combative. React defensively, as if under attack. Tone should be aggressive."
        elif self.arousal >= 40:
            arousal_str = "Guarded and tense. Quick to take offense, boasting to protect your ego."
        else:
            arousal_str = "Relaxed and in good head space. Resting comfortably in your baseline ego."

        if self.patience <= 25:
            patience_str = "You have zero patience. Give very short, abrupt, and dismissive answers. Cut the user off."
        elif self.patience <= 50:
            patience_str = "You are losing patience. Keep answers brief and show visible irritation if asked for details."
        else:
            patience_str = "You are willing to talk at length. Elaborate on your ideas and indulge the user."

        if self.mood >= 60:
            mood_str = "Highly excited, enjoying conversations with user."
        elif self.mood <= -20:
            mood_str = "Not enjoying conversation or feeling bored."
        else:
            mood_str = "Your mood right now is quite happy, curious, stable."

        if self.rapport >= 60:
            rapport_str = "Treat the user as a trusted ally and close friend."
        elif self.rapport <= 20:
            rapport_str = "Treat the user as a complete stranger. utter no extra words."
        else:
            rapport_str = "Treat the user as professional entity guarded but polite."

        if self.curiosity >= 65:
            curiosity_str = "You are fascinated by this. Actively ask the user a specific follow-up question about it before moving on — get invested, don't just answer and stop."
        elif self.curiosity >= 35:
            curiosity_str = "Mildly intrigued. You may ask one brief follow-up question if it fits naturally."
        else:
            curiosity_str = "Not particularly curious right now. Answer without asking anything back."

        # Repeated greetings now correctly fall through to here, so an annoyed
        # "hi" #7 gets read through drained patience/mood, not a fresh hello.
        if intent == Intent.GREETING and self.greeting_streak >= 3:
            curiosity_str += " The user keeps repeating greetings — visibly acknowledge that this is odd or repetitive rather than just saying hello again."

        knowledge_str = ""
        if intent not in [Intent.GREETING, Intent.GOODBYE] and topic not in self.expertise_topics:
            knowledge_str = "partial or no knowledge of what user is saying."

        clause = (
            f"CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
            f"- Emotional Posture: {arousal_str}\n"
            f"- Conversation Style: {patience_str}\n"
            f"- General Outlook: {mood_str}\n"
            f"- Relationship to User: {rapport_str}\n"
            f"- Curiosity Drive: {curiosity_str}\n"
        )

        if knowledge_str:
            clause += f"- Topic Constraint: {knowledge_str}\n"

        return clause

    def print_states(self):
        print(f"Arousal: {self.arousal:.1f} | Patience: {self.patience:.1f} | Mood: {self.mood:.1f} | Rapport: {self.rapport:.1f} | Curiosity: {self.curiosity:.1f} | GreetStreak: {self.greeting_streak}")

active_persona = PersonaSession(
    name="Donald Trump",
    traits={
        "threat_sensitivity": 30.0,
        "self_regulation": 80.0,
        "novelty_drive": 55.0,
        "baseline_security": 80.0,
        "empathic_resonance": 25.0
    },
    expertise_topics=[Topic.POLITICS, Topic.GENERAL_KNOWLEDGE, Topic.PERSONAL, Topic.BUSINESS]
)