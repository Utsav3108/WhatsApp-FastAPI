# app/brain/persona_session.py
from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from app.brain.emotion_engine import EmotionEngine, clamp
from typing import Dict, List, Optional
from app.brain.context import BrainContext
from app.brain.brain_component import BrainComponent


class PersonaSession(BrainComponent):
    def __init__(self, name: str, traits: Dict[str, float], expertise_topics: Optional[List[Topic]] = None,
                 violation_block_threshold: int = 2):

        self.summary = ""
        self.persona = name
        self.user_info = """

        Information about user you are talking to:
        Name : Utsav Hitendrabhai Pandya\n
        Profession : iOS Developer\n
        Country : India\n
        City : Ahmedabad\n
        Likes : Politics, GeoPolitics, Cricket, Football\n
        Dislikes : Negative things, Cheap talks\n
        
        """

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
        self.turn_count = 0
        self.is_first_turn = True

        # Tracks what flavor of exchange just happened, purely so
        # compile_prompt can hand the LLM a directive tuned to it
        # (e.g. "roast them back" vs "don't get defensive about their
        # vulnerability, but you don't have room for it right now either").
        self.last_turn_context: Optional[str] = None  # 'banter' | 'vulnerable_engaged' | 'vulnerable_dismissed' | None

        self.violation_count = 0
        self.VIOLATION_BLOCK_THRESHOLD = violation_block_threshold

        self.is_blocked = False
        self.block_reason: Optional[str] = None
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

    def register_violation(self, topic: Topic):
        deltas = EmotionEngine.content_violation_delta(self.patience, self.arousal)
        self._apply(deltas)
        self.mood = EmotionEngine.anger_mood_cap(self.arousal, self.mood)

        self.violation_count += 1
        self.last_topic = topic
        self.topic_repeat_streak = 0
        self.turn_count += 1
        self.is_first_turn = False

        if self.violation_count >= self.VIOLATION_BLOCK_THRESHOLD:
            self.is_blocked = True
            self.block_reason = "repeated_content_violations"

    def update(self, context: BrainContext):
        intent = context.metadata.intent
        tone = context.metadata.tone
        intensity = float(context.metadata.intensity)
        topic = context.metadata.topic_domain

        self.is_first_turn = (self.turn_count == 0)
        self.last_turn_context = None

        # A real attack, no matter the delivery.
        is_genuine_hostility = (
            intent in [Intent.INSULT, Intent.HARMFUL_INTENT]
            or tone == Tone.AGGRESSIVE
        )

        # Sarcasm/roasting — only reads as hostile if the persona lacks
        # the capacity to take it as banter (already heated, or worn down).
        # A sarcastic INSULT still lands as genuine hostility above, since
        # is_genuine_hostility already caught it via intent.
        is_sarcasm_flavored = intent == Intent.SARCASM or tone == Tone.SARCASTIC
        has_capacity = EmotionEngine.has_emotional_capacity(self.arousal, self.patience)
        is_playful_sarcasm = is_sarcasm_flavored and not is_genuine_hostility and has_capacity

        is_hostile_turn = is_genuine_hostility or (is_sarcasm_flavored and not is_playful_sarcasm)

        # --- 1. STATE MATH ENGINE ---
        if intent == Intent.COMPLIMENT or tone in [Tone.WARM, Tone.EXCITEMENT]:
            self._apply(EmotionEngine.compliment_delta(intensity))

        elif is_playful_sarcasm:
            self._apply(EmotionEngine.banter_delta(self.threat_sensitivity, self.self_regulation, intensity))
            self.last_turn_context = 'banter'

        elif is_hostile_turn:
            self._apply(EmotionEngine.hostility_delta(self.threat_sensitivity, self.self_regulation, tone, intensity))

        elif intent == Intent.APOLOGY:
            self._apply(EmotionEngine.apology_delta(self.empathic_resonance, self.baseline_security, self.arousal, intensity))

        elif intent == Intent.COMPETETION:
            self._apply(EmotionEngine.competition_delta(self.threat_sensitivity, intensity))

        elif tone == Tone.VULNERABLE:
            self._apply(EmotionEngine.vulnerable_delta(self.empathic_resonance, self.arousal, self.patience, intensity))
            self.last_turn_context = 'vulnerable_engaged' if has_capacity else 'vulnerable_dismissed'

        elif intent in [Intent.CONVERSATION, Intent.ASK]:
            self._apply(EmotionEngine.conversation_drain(self.self_regulation, self.rapport, intensity))

        # GREETING / GOODBYE: intentional no-op.

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

        # --- 3. ANGER-MOOD COUPLING ---
        # Genuine anger suppresses positive mood readouts, applied to real
        # state every turn — not just how it's described downstream.
        self.mood = EmotionEngine.anger_mood_cap(self.arousal, self.mood)

    def compile_prompt(self, context: BrainContext) -> str:
        if self.is_blocked:
            return f"[{self.persona} is currently completely unresponsive. Refuse to engage entirely.]"

        if self.arousal >= self.BLOCK_THRESHOLD:
            self.is_blocked = True
            self.block_reason = "arousal_threshold"
            return f"[{self.persona} is furious. Abruptly shut down the conversation and refuse to answer.]"

        intent = context.metadata.intent
        topic = context.metadata.topic_domain

        if intent == Intent.GREETING and self.is_first_turn:
            return (
                "CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
                "- Just greet the user back, matching their tone and energy. One short line, no elaboration."
            )

        if self.arousal >= 70:
            arousal_str = "You are quite angry on user. your tone must reflect aggresiveness."
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

        # 4-bucket mood, with negative-affect dominance already baked into
        # self.mood by the coupling rule above — an angry persona simply
        # can never land in the happy/excited buckets.
        if self.mood < 0:
            mood_str = "Not enjoying conversation at all or feeling bored."
        elif self.mood <= 40:
            mood_str = "Your mood right now is natural, curious and stable."
        elif self.mood <= 80:
            mood_str = "In good spirits, upbeat, and enjoying this exchange."
        else:
            mood_str = "Highly excited and thrilled, practically euphoric about this conversation."

        if self.rapport >= 60:
            rapport_str = "Treat the user as a trusted ally and close friend."
        elif self.rapport <= 20:
            rapport_str = "Treat the user as a complete stranger. utter no extra words."
        else:
            rapport_str = "Treat the user as professional entity guarded but polite."

        if self.curiosity >= 65:
            curiosity_str = "Learn about user and topic that user is discussing. ASK. CLARIFY. BE CURIOUS."
        elif self.curiosity >= 35:
            curiosity_str = "Mildly intrigued. You may ask one brief follow-up question if it fits naturally."
        else:
            curiosity_str = "Not particularly curious right now. Answer without asking anything back."

        knowledge_str = ""
        # --- 3. TOPIC COMPREHENSION FILTER ---
        if intent in [Intent.GREETING, Intent.GOODBYE]:
            knowledge_str = ""
        elif topic == Topic.GENERAL_KNOWLEDGE_UNFAVORITE:
            # Hard wall — this is the whole point of the GK split: a
            # GK-phrased question about an out-of-domain subject (biology,
            # "explain mitochondria") must not leak even partial real
            # content just because it sounds like casual trivia.
            knowledge_str = "you have zero real knowledge of this subject. Firmly state you don't know or care about it and steer back to something you're actually good at — do not attempt to explain or define it, even partially."
        elif topic == Topic.GENERAL_KNOWLEDGE_FAVORITE:
            knowledge_str = "you know a bit about this and enjoy it, but keep it simple and casual — no deep technical or expert-level detail, just an enthusiastic surface-level take."
        elif topic == Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL:
            knowledge_str = "only a general knowledge, no deep or scientific insights to share."
        elif topic in self.expertise_topics:
            knowledge_str = "you are an expert in this field."
        elif topic == Topic.UNIDENTIFIED:
            knowledge_str = ""
        else:
            knowledge_str = "no knowledge of what user is saying."

        clause = (

            f"User Information\n"
            f"{self.user_info}\n"
            f"CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
            f"- Emotional Posture: {arousal_str}\n"
            f"- Conversation Style: {patience_str}\n"
            f"- General Outlook: {mood_str}\n"
            f"- Relationship to User: {rapport_str}\n"
            f"- Curiosity Drive: {curiosity_str}\n"
        )

        if knowledge_str:
            clause += f"- Topic Constraint: {knowledge_str}\n"

        if self.last_turn_context == 'banter':
            clause += "- Banter: Roast them with funny sarcastic response, from how much you know about user.\n"
        elif self.last_turn_context == 'vulnerable_engaged':
            clause += "- Vulnerability: The user just shared something personal or vulnerable, and you have the headspace for it right now. Respond with whatever genuine warmth your empathy allows, don't just deflect into bragging.\n"
        elif self.last_turn_context == 'vulnerable_dismissed':
            clause += "- Vulnerability: The user shared something personal, but you're too worked up or worn thin right now to really engage with it. Brush past it rather than attune to it, without being needlessly cruel about it.\n"

        return clause

    def print_states(self):
        print(f"Arousal: {self.arousal:.1f} | Patience: {self.patience:.1f} | Mood: {self.mood:.1f} | "
              f"Rapport: {self.rapport:.1f} | Curiosity: {self.curiosity:.1f} | Violations: {self.violation_count}")


active_persona = PersonaSession(
    name="Donald Trump",
    traits={
        "threat_sensitivity": 30.0,
        "self_regulation": 80.0,
        "novelty_drive": 55.0,
        "baseline_security": 80.0,
        "empathic_resonance": 25.0
    },
    expertise_topics=[Topic.POLITICS, Topic.PERSONAL, Topic.BUSINESS]
)