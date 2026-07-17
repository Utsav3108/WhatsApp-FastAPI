from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from typing import Dict
from app.brain.context import BrainContext
from app.brain.brain_component import BrainComponent

class PersonaSession(BrainComponent):
    def __init__(self, name: str, traits: Dict[str, float]):
        self.persona = name
        
        # 1. Constant Traits
        self.threat_sensitivity = traits.get('threat_sensitivity', 50.0)
        self.self_regulation = traits.get('self_regulation', 50.0)
        self.novelty_drive = traits.get('novelty_drive', 50.0)
        self.baseline_security = traits.get('baseline_security', 50.0)
        self.empathic_resonance = traits.get('empathic_resonance', 50.0)
        
        # 2. Computed State
        self.arousal = max(0.0, 30.0 - (self.baseline_security / 4.0))
        self.patience = min(100.0, 40.0 + (self.self_regulation / 2.0))
        self.mood = 0.0
        self.rapport = 0.0
        
        # Session locks
        self.is_blocked = False
        self.BLOCK_THRESHOLD = 100


    def update(self, context : BrainContext):
        intent = context.metadata.intent
        tone = context.metadata.tone
        intensity = float(context.metadata.intensity)

        # --- 1. STATE MATH ENGINE ---
        
        # Contextual Modifiers based on Intent + Tone pairings
        if intent == Intent.COMPLIMENT or tone == Tone.WARM:
            self.mood = min(100.0, self.mood + (intensity * 0.25))
            self.rapport = min(100.0, self.rapport + (intensity * 0.15))
            self.arousal = max(0.0, self.arousal - (intensity * 0.1))
            self.patience = min(100.0, self.patience + (intensity * 0.1))
                    
        elif intent in [Intent.INSULT, Intent.HARMFUL_INTENT] or tone in [Tone.AGGRESSIVE, Tone.SARCASTIC]:
            # Sarcasm or aggression multiplies threat response
            tone_multiplier = 1.5 if tone in [Tone.AGGRESSIVE, Tone.SARCASTIC] else 1.0
            self.arousal += (self.threat_sensitivity / 100.0) * intensity * tone_multiplier
            
            sr_divisor = self.self_regulation if self.self_regulation > 0 else 1
            self.patience = max(0.0, self.patience - ((intensity * tone_multiplier) / sr_divisor))
            self.mood = max(-100.0, self.mood - (intensity * 0.2))
            
        elif intent == Intent.APOLOGY:
            # Apologies work less effectively if persona arousal is already past extreme thresholds
            anger_modifier = 0.5 if self.arousal >= 70.0 else 1.0
            forgiveness_rate = self.empathic_resonance * (self.baseline_security / 100.0) * anger_modifier
            self.arousal = max(0.0, self.arousal - (forgiveness_rate / 100.0) * intensity)
            self.patience = min(100.0, self.patience + (intensity * 0.1))
            
        elif intent in [Intent.CONVERSATION, Intent.ASK]:
            # Temperament: how fast THIS persona tires, period (self_regulation-driven)
            base_drain = 3.0 - (self.self_regulation / 50.0)
            # Relationship: discount for THIS specific person (rapport-driven)
            rapport_discount = self.rapport / 100.0  # 0 → no discount, 1.0 → fully offset
            drain = max(0.0, base_drain - rapport_discount)
            self.patience = max(0.0, self.patience - drain)
            self.mood = min(100.0, self.mood + (intensity * 0.05))

        self.arousal = min(100.0, self.arousal)

    def compile_prompt(self, context : BrainContext) -> str:
        """
        Calculates internal changes utilizing the dual-axis intent and tone 
        modifiers alongside intensity data, translating them to strict behavioral directives.
        """
        if self.is_blocked:
            return f"[{self.persona} is currently completely unresponsive. Refuse to engage entirely.]"

        if self.arousal >= self.BLOCK_THRESHOLD:
            self.is_blocked = True
            return f"[{self.persona} is furious. Abruptly shut down the conversation and refuse to answer.]"

        # --- 2. SEMANTIC TRANSLATION ---
        
        if self.arousal >= 70:
            arousal_str = "Highly agitated and combative. React defensively, as if under attack. Tone should be aggressive."
        elif self.arousal >= 40:
            arousal_str = "Guarded and tense. Quick to take offense, boasting to protect your ego."
        else:
            arousal_str = "Relaxed and entirely unbothered. Resting comfortably in your baseline ego."

        if self.patience <= 25:
            patience_str = "You have zero patience. Give very short, abrupt, and dismissive answers. Cut the user off."
        elif self.patience <= 50:
            patience_str = "You are losing patience. Keep answers brief and show visible irritation if asked for details."
        else:
            patience_str = "You are willing to talk at length. Elaborate on your ideas and indulge the user."

        if self.mood >= 60:
            mood_str = "Magnanimous, highly optimistic, and focusing on your grand victories."
        elif self.mood <= -20: 
            mood_str = "Sour, aggrieved, and focused on how unfairly you are being treated."
        else:
            mood_str = "Maintaining a standard, baseline disposition."

        if self.rapport >= 60:
            rapport_str = "Treat the user as a trusted ally and close friend."
        elif self.rapport <= 20:
            rapport_str = "Treat the user as a complete stranger. utter no extra words."
        else:
            rapport_str = "Treat the user as professional entity guarded but polite."

        # --- 3. TOPIC COMPREHENSION FILTER ---
        knowledge_str = "Respond normally within the scope of your persona knowledge."
        if self.persona == "Donald Trump":
            if context.metadata.topic_domain in [Topic.POLITICS, Topic.GENERAL_KNOWLEDGE, Topic.PERSONAL, Topic.NONSENSE, Topic.REAL_ESTATE]:
                knowledge_str = "You treat this area as your paramount area of expertise. Speak with total, absolute hyperbole."

            else :
                knowledge_str = "DENY TO ANSWER as you do not know anything about this subject or topic staying in charector."
        clause = (
            f"CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
            f"- Emotional Posture: {arousal_str}\n"
            f"- Conversation Style: {patience_str}\n"
            f"- General Outlook: {mood_str}\n"
            f"- Relationship to User: {rapport_str}\n"
            f"- Topic Constraint: {knowledge_str}\n"
        )
        
        return clause

    def print_states(self):
        print(f"Arousal: {self.arousal:.1f} | Patience: {self.patience:.1f} | Mood: {self.mood:.1f} | Rapport: {self.rapport:.1f}")  
