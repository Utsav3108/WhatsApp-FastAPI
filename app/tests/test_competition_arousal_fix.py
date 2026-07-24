# Same style as test_curiosity_zones.py: plain synchronous unittest.TestCase,
# no DB/Redis fixture — PersonaSession/EmotionEngine need neither to import
# or exercise.
import unittest

from app.brain.emotion_engine import EmotionEngine
from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from app.brain.context import BrainContext
from app.persona.persona_session import PersonaSession


def make_metadata(intent=Intent.CONVERSATION, tone=Tone.NEUTRAL, intensity=30,
                   topic_domain=Topic.GENERAL_KNOWLEDGE_FAVORITE, language="en") -> UserMessageMetaDataResponse:
    return UserMessageMetaDataResponse(
        intent=intent, tone=tone, intensity=intensity, topic_domain=topic_domain, language=language
    )


# Trump's live traits (app/persona/persona_session.py's active_persona singleton)
TRUMP_TRAITS = {
    "threat_sensitivity": 30.0,
    "self_regulation": 80.0,
    "novelty_drive": 55.0,
    "baseline_security": 80.0,
    "empathic_resonance": 25.0,
}


class TestHostileTurnClassification(unittest.TestCase):

    def test_genuine_insult_routes_to_hostility_not_competition(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.INSULT, tone=Tone.NEUTRAL, intensity=75))
        arousal_before = session.arousal
        session.update(context)
        # hostility_delta's tone_multiplier=1.0 (NEUTRAL) -> arousal delta = (30/100)*75*1.0 = 22.5
        self.assertAlmostEqual(session.arousal - arousal_before, 22.5)

    def test_competitive_aggressive_routes_to_competition_with_small_arousal_delta(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.COMPETETION, tone=Tone.AGGRESSIVE, intensity=75))
        arousal_before = session.arousal
        session.update(context)
        # new competition_delta: (30/100)*75*0.1 = 2.25, NOT hostility_delta's (30/100)*75*1.5 = 33.75
        self.assertAlmostEqual(session.arousal - arousal_before, 2.25)

    def test_pure_aggressive_tone_no_competitive_intent_routes_to_hostility(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.CONVERSATION, tone=Tone.AGGRESSIVE, intensity=75))
        arousal_before = session.arousal
        session.update(context)
        # hostility_delta's tone_multiplier=1.5 (AGGRESSIVE) -> arousal delta = (30/100)*75*1.5 = 33.75
        self.assertAlmostEqual(session.arousal - arousal_before, 33.75)

    def test_sarcastic_tone_no_competitive_intent_routes_to_banter(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.CONVERSATION, tone=Tone.SARCASTIC, intensity=75))
        arousal_before = session.arousal
        session.update(context)
        # banter_delta: (30/100)*75*0.05 = 1.125, distinct from both competition_delta (2.25) and hostility_delta (33.75)
        self.assertAlmostEqual(session.arousal - arousal_before, 1.125)
        self.assertEqual(session.last_turn_context, 'banter')

    def test_competitive_sarcastic_does_not_route_to_hostility(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.COMPETETION, tone=Tone.SARCASTIC, intensity=75))
        arousal_before = session.arousal
        session.update(context)
        # competition_delta: (30/100)*75*0.1 = 2.25 -- must NOT be hostility_delta's 1.5x-multiplied 33.75
        self.assertAlmostEqual(session.arousal - arousal_before, 2.25)
        self.assertIsNone(session.last_turn_context)  # not routed through banter_delta either

    def test_competitive_sarcastic_does_not_trigger_curiosity_hostile_penalty(self):
        session = PersonaSession(name="Test", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS])
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.COMPETETION, tone=Tone.SARCASTIC, intensity=75))
        session.update(context)
        # a -20 flat hostile-turn hit would drive curiosity negative (clamped to 0) from a 0.0 start;
        # the zone-based CURIOSITY-zone formula should instead produce a positive delta.
        self.assertGreater(session.curiosity, 0.0)


class TestConversationLogRegression(unittest.TestCase):
    """
    Replays the exact 9-turn intent/tone/intensity sequence from app/logs.txt
    (real Trump persona conversation, cricket/sports trash-talk) that
    originally hard-clamped arousal to 100 and blocked the conversation.
    """

    LOG_TURNS = [
        (Intent.COMPETETION, Tone.SARCASTIC, 75),
        (Intent.CONVERSATION, Tone.WARM, 15),
        (Intent.ASK, Tone.CURIOUS, 30),
        (Intent.COMPETETION, Tone.AGGRESSIVE, 75),
        (Intent.COMPETETION, Tone.SARCASTIC, 75),
        (Intent.ASK, Tone.CURIOUS, 20),
        (Intent.COMPETETION, Tone.SARCASTIC, 75),
        (Intent.SARCASM, Tone.SARCASTIC, 75),
        (Intent.COMPETETION, Tone.AGGRESSIVE, 75),
    ]
    COMPETITIVE_TURN_INDICES = {0, 3, 4, 6, 8}

    def _replay_log(self):
        session = PersonaSession(name="Trump", traits=TRUMP_TRAITS, expertise_topics=[Topic.POLITICS, Topic.PERSONAL, Topic.BUSINESS])
        curiosity_history = [session.curiosity]
        for intent, tone, intensity in self.LOG_TURNS:
            context = BrainContext(question="q", metadata=make_metadata(intent=intent, tone=tone, intensity=intensity))
            session.update(context)
            curiosity_history.append(session.curiosity)
        return session, curiosity_history

    def test_arousal_never_reaches_block_threshold_across_log(self):
        session, _ = self._replay_log()
        # traced expected final arousal ~20.9; generous upper bound so this
        # doesn't become brittle against minor future formula tuning
        self.assertLess(session.arousal, 40.0)
        self.assertFalse(session.is_blocked)

    def test_no_competitive_turn_triggers_flat_hostile_penalty(self):
        _, curiosity_history = self._replay_log()
        for idx in self.COMPETITIVE_TURN_INDICES:
            delta = curiosity_history[idx + 1] - curiosity_history[idx]
            # a -20 flat hostile hit would be a large drop; every competitive
            # turn in this log should instead show a positive accrual
            self.assertGreater(delta, 0.0, f"turn {idx} (competitive) unexpectedly dropped curiosity")

    def test_final_curiosity_exceeds_old_buggy_ceiling(self):
        session, _ = self._replay_log()
        # old buggy log never sustainably cleared its turn-3 peak of ~25.6;
        # traced expected final value under the fix is ~47.6
        self.assertGreater(session.curiosity, 35.0)


if __name__ == "__main__":
    unittest.main()
