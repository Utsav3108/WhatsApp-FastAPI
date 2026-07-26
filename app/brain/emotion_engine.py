# app/brain/emotion_engine.py
import math
from enum import Enum

from app.brain.schemas import Tone, Topic


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class CuriosityZone(str, Enum):
    """
    Derived internal concept (never produced by the classifier — Topic is),
    so it lives here rather than in schemas.py alongside the classifier's
    actual output vocabulary (Intent/Tone/Topic).
    """
    APATHY = "apathy"                # GK_UNFAVORITE, a real-domain topic outside expertise, or UNIDENTIFIED
    CURIOSITY = "curiosity"          # GK_FAVORITE — partial familiarity, real info gap (peak)
    BOREDOM = "boredom"              # topic in expertise_topics, deep/technical register — closed gap
    ROUTED_AROUND = "routed_around"  # PERSONAL / GK_LIFE_OR_PERSONAL — rapport, not info-gap
    ANACHRONISTIC = "anachronistic"  # requires_post_cutoff_knowledge — beyond the persona's lifetime,
                                      # the largest possible information gap this system can represent.
                                      # Deliberately not folded into APATHY: apathy's framing (disinterest,
                                      # ego-driven bridging) is the wrong register for "something from
                                      # decades in my future" — closer to maximal CURIOSITY, just more so.


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
    def half_life_hours(self_regulation: float, threat_sensitivity: float) -> float:
        """
        Wall-clock recovery rate — a third, distinct job for the same two
        traits that already drive in-conversation arousal rise
        (hostility_delta) and patience drain (banter_delta/
        competition_delta): how fast this persona cools down BETWEEN
        conversations, not how reactive or thin-skinned they are DURING
        one. High self_regulation + low threat_sensitivity -> short
        half-life, fast cooldown (a secure, even-tempered persona lets
        things go quickly). Low self_regulation + high threat_sensitivity
        -> long half-life, slow cooldown (a grudge-holder still simmering
        the next day with zero new provocation).
        """
        return 24.0 * (self_regulation / max(threat_sensitivity, 1.0))

    @staticmethod
    def time_cooldown_delta(arousal: float, mood: float, patience: float,
                             self_regulation: float, threat_sensitivity: float,
                             baseline_security: float, elapsed_hours: float) -> dict:
        """
        Pure function — no side effects, no DB awareness, same contract as
        every other EmotionEngine method. Models wall-clock decay BETWEEN
        messages (distinct from and unaffected by the turn-based deltas
        above): arousal relaxes toward 0, mood drifts toward neutral (0),
        patience regenerates toward 100 (rate gated by baseline_security —
        a secure persona recovers composure faster than an insecure one
        given the same quiet time). rapport is DELIBERATELY excluded —
        it's durable relationship memory, not mood, and does not decay
        with time.
        """
        if elapsed_hours <= 0:
            return {}

        half_life = EmotionEngine.half_life_hours(self_regulation, threat_sensitivity)
        cooldown = 1.0 - math.exp(-elapsed_hours / half_life)

        new_arousal = arousal - (arousal * cooldown)
        new_mood = mood * (1.0 - cooldown)
        new_patience = patience + (100.0 - patience) * cooldown * (baseline_security / 100.0)

        return {
            "arousal": new_arousal - arousal,
            "mood": new_mood - mood,
            "patience": new_patience - patience,
        }

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
        capacity-gated in persona_session.update(). Same rebalancing logic
        as competition_delta: genuine roasting is not a threat signal, so
        arousal cost is near-zero and patience (the "the joke overstayed
        its welcome" resource) carries the primary cost, paired with a
        mood boost since a good roast is fun, not a wound. If it goes on
        long enough to drain patience below the capacity floor, this same
        message would start reading as hostile on the next turn — banter
        that overstays its welcome legitimately becomes annoying.
        """
        sr_divisor = self_regulation if self_regulation > 0 else 1
        return {
            "arousal": (threat_sensitivity / 100.0) * intensity * 0.05,
            "patience": -(intensity * 0.35) / sr_divisor,
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
    def competition_delta(threat_sensitivity: float, self_regulation: float, intensity: float) -> dict:
        """
        A competitive dig/challenge — not a real attack. Arousal should
        model threat detection ("am I under attack"); competitive banter
        isn't a threat, it's effortful — parrying jabs costs energy/
        stamina, not vigilance. That maps onto patience (a depleting
        resource) far more naturally than arousal (a threat gauge), so
        patience carries the primary cost here and arousal only a small
        residual.
        """
        sr_divisor = self_regulation if self_regulation > 0 else 1
        return {
            "arousal": (threat_sensitivity / 100.0) * intensity * 0.1,
            "patience": -(intensity * 0.35) / sr_divisor,
            "mood": intensity * 0.08,
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
    def classify_curiosity_zone(topic: Topic, requires_post_cutoff_knowledge: bool = False) -> "CuriosityZone":
        """
        Maps the classifier's topic label onto Information Gap Theory's
        curiosity zones. Domain-membership (in/out of the persona's
        expertise) is now resolved INSIDE the classifier call itself (EXPERT
        vs NOT_AN_EXPERT), so this is a straight lookup table — no
        expertise_topics needed here anymore. PERSONAL and
        GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL map to ROUTED_AROUND: they're a
        rapport mechanism, not an information-gap mechanism, and stay
        outside the zone system.
        """
        if requires_post_cutoff_knowledge:
            # Checked FIRST — overrides normal zone resolution the same way
            # PersonaSession.compile_prompt()'s knowledge-gating override
            # does, and for the same reason: this can be True regardless of
            # what topic also resolved to.
            return CuriosityZone.ANACHRONISTIC
        if topic in (Topic.PERSONAL, Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL):
            return CuriosityZone.ROUTED_AROUND
        if topic == Topic.GENERAL_KNOWLEDGE_FAVORITE:
            return CuriosityZone.CURIOSITY
        if topic in (Topic.GENERAL_KNOWLEDGE_UNFAVORITE, Topic.NOT_AN_EXPERT):
            return CuriosityZone.APATHY
        if topic == Topic.EXPERT:
            return CuriosityZone.BOREDOM
        return CuriosityZone.APATHY  # UNIDENTIFIED or unexpected value — defensive default

    @staticmethod
    def curiosity_delta(novelty_drive: float, intensity: float, zone: "CuriosityZone", is_new_topic: bool,
                         tone: Tone, topic_repeat_streak: int, is_hostile_turn: bool,
                         zone_base: float = 15.0,
                         repeat_decay_floor: float = 0.3,
                         repeat_decay_step: float = 0.15,
                         apathy_decay: float = 5.0,
                         boredom_decay: float = 2.0,
                         violated_expectations_intensity: float = 70.0,
                         violated_expectations_bonus: float = 20.0) -> float:
        """
        Curiosity peaks on *partial* familiarity, not total ignorance or
        total mastery (Information Gap Theory) — starting constants below,
        pending verification against real conversation logs same as the
        rest of this file's formulas.
        """
        if is_hostile_turn:
            return -20.0

        novelty_factor = novelty_drive / 100.0
        stimulation = 0.0

        if zone == CuriosityZone.ROUTED_AROUND:
            # Unchanged legacy behavior: bump only on topic change.
            if is_new_topic:
                stimulation = novelty_factor * zone_base

        elif zone == CuriosityZone.CURIOSITY:
            # Sustains every turn the topic stays in this zone (not just
            # the turn it's first raised), decaying via topic_repeat_streak
            # — the "Routine and Habit" mechanic, reconnected here instead
            # of the old flat in-expertise bonus it used to be wired to.
            repetition_fatigue = max(repeat_decay_floor, 1.0 - topic_repeat_streak * repeat_decay_step)
            stimulation = novelty_factor * zone_base * repetition_fatigue

        elif zone == CuriosityZone.BOREDOM:
            if intensity >= violated_expectations_intensity:
                # Violated-expectations exception: the topic itself isn't
                # novel, but this specific claim is unusually charged.
                stimulation = novelty_factor * violated_expectations_bonus
            else:
                stimulation = -(boredom_decay * (1 - novelty_factor))

        elif zone == CuriosityZone.ANACHRONISTIC:
            # No repetition-fatigue decay applied here unlike CURIOSITY —
            # every distinct post-cutoff topic is presumably equally novel
            # to a persona who has never encountered ANY of it, so
            # topic_repeat_streak isn't a meaningful signal in this zone.
            # Higher weight than CURIOSITY's peak — arguably the largest
            # information gap this system can represent.
            stimulation = novelty_factor * (zone_base * 1.5)

        else:  # APATHY
            stimulation = -(apathy_decay * (1 - novelty_factor))

        if tone == Tone.CURIOUS:
            stimulation *= 1.3

        return stimulation