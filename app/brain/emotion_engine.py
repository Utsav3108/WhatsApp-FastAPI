# app/brain/emotion_engine.py
from app.brain.schemas import Tone


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class EmotionEngine:
    """
    Pure, stateless emotion-delta calculators. Each method takes only the values
    it needs and returns a dict of deltas (or a single float delta) — no side
    effects, no reference to PersonaSession. Keeps every lever independently
    testable and independently tunable.
    """

    @staticmethod
    def compliment_delta(intensity: float) -> dict:
        return {
            "mood": intensity * 0.25,
            "rapport": intensity * 0.15,
            "arousal": -(intensity * 0.1),
            "patience": intensity * 0.1,
        }

    @staticmethod
    def hostility_delta(threat_sensitivity: float, self_regulation: float, tone: Tone, intensity: float) -> dict:
        tone_multiplier = 1.5 if tone in [Tone.AGGRESSIVE, Tone.SARCASTIC] else 1.0
        sr_divisor = self_regulation if self_regulation > 0 else 1
        return {
            "arousal": (threat_sensitivity / 100.0) * intensity * tone_multiplier,
            "patience": -((intensity * tone_multiplier) / sr_divisor),
            "mood": -(intensity * 0.2),
        }

    @staticmethod
    def apology_delta(empathic_resonance: float, baseline_security: float, current_arousal: float, intensity: float) -> dict:
        anger_modifier = 0.5 if current_arousal >= 70.0 else 1.0
        forgiveness_rate = empathic_resonance * (baseline_security / 100.0) * anger_modifier
        return {
            "arousal": -((forgiveness_rate / 100.0) * intensity),
            "patience": intensity * 0.1,
        }

    @staticmethod
    def conversation_drain(self_regulation: float, rapport: float, intensity: float) -> dict:
        base_drain = 3.0 - (self_regulation / 50.0)
        rapport_discount = rapport / 100.0
        drain = max(0.0, base_drain - rapport_discount)
        return {
            "patience": -drain,
            "mood": intensity * 0.05,
        }

    @staticmethod
    def greeting_delta(self_regulation: float, threat_sensitivity: float, greeting_streak: int) -> dict:
        """
        First greeting of the session is handled separately in compile_prompt
        (bypasses this entirely). This only fires for repeats within a session —
        each additional "hi" reads as odd/testing patience, worse for
        short-fused personas, and enough repeats starts to feel like being
        trolled rather than just tiresome.
        """
        if greeting_streak <= 0:
            return {"patience": 0.0, "mood": 0.0, "arousal": 0.0}

        irritation_factor = 1.0 + (1.0 - self_regulation / 100.0)  # 1.0 patient → 2.0 short-fused
        patience_hit = min(greeting_streak * 1.5 * irritation_factor, 20.0)
        mood_hit = min(greeting_streak * 0.8, 10.0) if greeting_streak >= 3 else 0.0

        # sustained pointless repetition (6+) starts to read as deliberate
        # trolling, not just tedium — a small arousal nudge, scaled by
        # how easily this persona reads things as provocation
        arousal_hit = 0.0
        if greeting_streak >= 6:
            arousal_hit = min((greeting_streak - 5) * (threat_sensitivity / 100.0), 10.0)

        return {"patience": -patience_hit, "mood": -mood_hit, "arousal": arousal_hit}

    @staticmethod
    def curiosity_delta(
        novelty_drive: float,
        intensity: float,
        in_expertise: bool,
        is_new_topic: bool,
        tone: Tone,
        topic_repeat_streak: int,
        is_hostile_turn: bool,
    ) -> float:
        if is_hostile_turn:
            return -20.0

        novelty_factor = novelty_drive / 100.0
        stimulation = 0.0

        if in_expertise and intensity >= 40:
            repetition_fatigue = max(0.3, 1.0 - (topic_repeat_streak * 0.15))
            stimulation += novelty_factor * (intensity * 0.3) * repetition_fatigue

        if is_new_topic:
            stimulation += novelty_factor * 15.0

        if tone == Tone.CURIOUS:
            stimulation *= 1.3

        if stimulation == 0.0 and not is_new_topic and not in_expertise:
            return -(5.0 * (1 - novelty_factor))

        return stimulation