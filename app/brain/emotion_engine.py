# app/brain/emotion_engine.py
from app.brain.schemas import Tone


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class EmotionEngine:
    """
    Pure, stateless emotion-delta calculators. Each method takes only the
    values it needs and returns a dict of deltas — no side effects, no
    reference to PersonaSession.
    """

    @staticmethod
    def has_emotional_capacity(arousal: float, patience: float,
                                arousal_ceiling: float = 70.0, patience_floor: float = 25.0) -> bool:
        """
        Shared gate: can this persona engage generously right now, or are
        they too heated / too worn down to have bandwidth for anything
        beyond self-protection? Same thresholds used elsewhere in the
        prompt (70 = "quite angry", 25 = "zero patience"), reused here
        rather than inventing new magic numbers.
        """
        return arousal < arousal_ceiling and patience > patience_floor

    @staticmethod
    def anger_mood_cap(arousal: float, mood: float, threshold: float = 70.0) -> float:
        """
        Negative-affect dominance: genuine anger crowds out positive mood,
        regardless of what else landed this turn. Applied every turn, not
        just at display time, so mood doesn't silently stay inflated
        underneath an angry directive and snap back the instant arousal dips.
        """
        return min(mood, 0.0) if arousal > threshold else mood

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
    def banter_delta(threat_sensitivity: float, self_regulation: float, intensity: float) -> dict:
        """
        Playful sarcasm/roasting the persona has the standing to enjoy —
        capacity-gated in persona_session.update(). Light stimulation, not
        a threat: a little arousal (there's an edge to good banter), a
        little patience cost, but paired with a mood boost since a good
        roast is fun, not a wound. If it goes on long enough to drain
        patience below the capacity floor, this same message would start
        reading as hostile on the next turn — banter that overstays its
        welcome legitimately becomes annoying.
        """
        sr_divisor = self_regulation if self_regulation > 0 else 1
        return {
            "arousal": (threat_sensitivity / 100.0) * intensity * 0.3,
            "patience": -(intensity * 0.3) / sr_divisor,
            "mood": intensity * 0.1,
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
    def vulnerable_delta(empathic_resonance: float, arousal: float, patience: float, intensity: float) -> dict:
        """
        Someone sharing something vulnerable. Gated by the same capacity
        check as banter: a persona that's already too heated or too worn
        down doesn't have the bandwidth to attune to someone else's
        difficulty — being confronted with it while dysregulated reads as
        one more demand, not an invitation to connect.
        """
        if not EmotionEngine.has_emotional_capacity(arousal, patience):
            return {"patience": -(intensity * 0.05)}

        empathy_factor = empathic_resonance / 100.0
        return {
            "mood": -(intensity * 0.1 * empathy_factor),   # catching some of their difficulty
            "rapport": intensity * 0.2 * empathy_factor,    # being let in strengthens the bond
            "arousal": -(intensity * 0.05 * empathy_factor),
        }

    @staticmethod
    def competition_delta(threat_sensitivity: float, intensity: float) -> dict:
        """
        A competitive dig/challenge — not a real attack, so arousal rises
        much more gently than hostility_delta (0.4x weighting), and it's
        stimulating rather than purely threatening, so mood ticks up too.
        """
        return {
            "arousal": (threat_sensitivity / 100.0) * intensity * 0.4,
            "mood": intensity * 0.05,
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
    def content_violation_delta(current_patience: float, current_arousal: float,
                                  patience_ceiling: float = 50.0, arousal_floor: float = 50.0) -> dict:
        new_patience = min(current_patience, patience_ceiling)
        new_arousal = max(current_arousal, arousal_floor)
        return {
            "patience": new_patience - current_patience,
            "arousal": new_arousal - current_arousal,
        }

    @staticmethod
    def curiosity_delta(novelty_drive: float, intensity: float, in_expertise: bool, is_new_topic: bool,
                         tone: Tone, topic_repeat_streak: int, is_hostile_turn: bool) -> float:
        if is_hostile_turn:
            return -20.0

        novelty_factor = novelty_drive / 100.0
        stimulation = 0.0

        # if in_expertise and intensity >= 40:
        #     repetition_fatigue = max(0.3, 1.0 - (topic_repeat_streak * 0.15))
        #     stimulation += novelty_factor * (intensity * 0.3) * repetition_fatigue

        if is_new_topic:
            stimulation += novelty_factor * 15.0

        if tone == Tone.CURIOUS:
            stimulation *= 1.3

        if stimulation == 0.0 and not is_new_topic and not in_expertise:
            return -(5.0 * (1 - novelty_factor))

        return stimulation