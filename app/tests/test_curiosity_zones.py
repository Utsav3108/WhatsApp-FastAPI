# These tests are plain, synchronous unittest.TestCase — a departure from
# the rest of this suite (test_categories.py, test_challenges.py,
# test_profile_deletion.py), which are all IsolatedAsyncioTestCase with an
# in-memory SQLite fixture for DB-touching features. EmotionEngine and
# PersonaSession need neither DB nor Redis to import or exercise, so no
# async setup / fixture is needed here.
import unittest

from app.brain.emotion_engine import EmotionEngine, CuriosityZone
from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from app.brain.context import BrainContext
from app.persona.persona_session import PersonaSession


def make_metadata(intent=Intent.CONVERSATION, tone=Tone.NEUTRAL, intensity=30,
                   topic_domain=Topic.PERSONAL, language="en") -> UserMessageMetaDataResponse:
    return UserMessageMetaDataResponse(
        intent=intent, tone=tone, intensity=intensity, topic_domain=topic_domain, language=language
    )


class TestClassifyCuriosityZone(unittest.TestCase):

    def test_favorite_topic_is_curiosity_zone(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.GENERAL_KNOWLEDGE_FAVORITE, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.CURIOSITY)

    def test_unfavorite_topic_is_apathy_zone(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.GENERAL_KNOWLEDGE_UNFAVORITE, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.APATHY)

    def test_expertise_topic_is_boredom_zone(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.POLITICS, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.BOREDOM)

    def test_non_expertise_real_domain_topic_is_apathy_zone(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.SCIENCE, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.APATHY)

    def test_personal_topic_routed_around_even_when_in_expertise_topics(self):
        # Ordering regression guard: PERSONAL must be checked before
        # expertise-topic membership, or a persona with PERSONAL in its
        # expertise_topics (e.g. Trump) would get misrouted into Boredom.
        zone = EmotionEngine.classify_curiosity_zone(Topic.PERSONAL, [Topic.PERSONAL])
        self.assertEqual(zone, CuriosityZone.ROUTED_AROUND)

    def test_life_or_personal_topic_is_routed_around(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.ROUTED_AROUND)

    def test_unidentified_topic_is_apathy_zone(self):
        zone = EmotionEngine.classify_curiosity_zone(Topic.UNIDENTIFIED, [Topic.POLITICS])
        self.assertEqual(zone, CuriosityZone.APATHY)


class TestCuriosityDelta(unittest.TestCase):

    def test_hostile_turn_returns_flat_penalty_regardless_of_zone(self):
        for zone in CuriosityZone:
            with self.subTest(zone=zone):
                delta = EmotionEngine.curiosity_delta(
                    novelty_drive=80, intensity=90, zone=zone, is_new_topic=True,
                    tone=Tone.AGGRESSIVE, topic_repeat_streak=3, is_hostile_turn=True,
                )
                self.assertEqual(delta, -20.0)

    def test_apathy_zone_produces_low_or_negative_delta(self):
        delta = EmotionEngine.curiosity_delta(
            novelty_drive=50, intensity=30, zone=CuriosityZone.APATHY, is_new_topic=True,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertAlmostEqual(delta, -2.5)

    def test_curiosity_zone_sustains_and_decays_across_repeat_streak(self):
        d0 = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        d2 = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=2, is_hostile_turn=False,
        )
        d4 = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=4, is_hostile_turn=False,
        )
        self.assertGreater(d0, d2)
        self.assertGreater(d2, d4)
        self.assertGreater(d4, 0)

    def test_curiosity_zone_delta_floors_at_repeat_decay_floor(self):
        d10 = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=10, is_hostile_turn=False,
        )
        d20 = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=20, is_hostile_turn=False,
        )
        self.assertAlmostEqual(d10, d20)
        self.assertAlmostEqual(d10, 100 / 100.0 * 15.0 * 0.3)

    def test_boredom_zone_default_is_low(self):
        apathy_delta = EmotionEngine.curiosity_delta(
            novelty_drive=50, intensity=30, zone=CuriosityZone.APATHY, is_new_topic=True,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        boredom_delta = EmotionEngine.curiosity_delta(
            novelty_drive=50, intensity=30, zone=CuriosityZone.BOREDOM, is_new_topic=True,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertAlmostEqual(boredom_delta, -1.0)
        self.assertLess(abs(boredom_delta), abs(apathy_delta))

    def test_boredom_zone_violated_expectations_spike_above_threshold(self):
        delta = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=70, zone=CuriosityZone.BOREDOM, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertAlmostEqual(delta, 20.0)
        self.assertGreater(delta, 0)

    def test_boredom_zone_no_spike_below_intensity_threshold(self):
        delta = EmotionEngine.curiosity_delta(
            novelty_drive=50, intensity=69, zone=CuriosityZone.BOREDOM, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertLess(delta, 0)

    def test_curious_tone_multiplier_applies_across_zones(self):
        neutral_delta = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=50, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        curious_delta = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=50, zone=CuriosityZone.CURIOSITY, is_new_topic=False,
            tone=Tone.CURIOUS, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertAlmostEqual(curious_delta, neutral_delta * 1.3)

    def test_routed_around_zone_only_spikes_on_new_topic(self):
        new_topic_delta = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.ROUTED_AROUND, is_new_topic=True,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        same_topic_delta = EmotionEngine.curiosity_delta(
            novelty_drive=100, intensity=30, zone=CuriosityZone.ROUTED_AROUND, is_new_topic=False,
            tone=Tone.NEUTRAL, topic_repeat_streak=0, is_hostile_turn=False,
        )
        self.assertGreater(new_topic_delta, 0)
        self.assertEqual(same_topic_delta, 0.0)


class TestPersonaSessionCuriosityIntegration(unittest.TestCase):

    def test_capacity_gate_suppresses_curiosity_directive_when_aroused(self):
        session = PersonaSession(name="Test", traits={}, expertise_topics=[Topic.POLITICS])
        session.curiosity = 80.0
        session.arousal = 75.0  # above the has_emotional_capacity ceiling of 70
        session.patience = 50.0
        session.turn_count = 1  # not first turn, so the GREETING short-circuit doesn't apply

        context = BrainContext(question="test", metadata=make_metadata(
            intent=Intent.CONVERSATION, topic_domain=Topic.POLITICS
        ))
        clause = session.compile_prompt(context)

        self.assertIn("Not particularly curious right now", clause)
        self.assertNotIn("ASK. CLARIFY. BE CURIOUS", clause)
        self.assertEqual(session.curiosity, 80.0)  # untouched — only the directive changes

    def test_favorite_topic_stronger_followup_than_expertise_topic(self):
        traits = {"novelty_drive": 100.0}

        session_fav = PersonaSession(name="Fav", traits=traits, expertise_topics=[Topic.POLITICS])
        session_fav.update(BrainContext(question="q", metadata=make_metadata(
            intent=Intent.ASK, intensity=30, topic_domain=Topic.GENERAL_KNOWLEDGE_FAVORITE
        )))

        session_bore = PersonaSession(name="Bore", traits=traits, expertise_topics=[Topic.POLITICS])
        session_bore.update(BrainContext(question="q", metadata=make_metadata(
            intent=Intent.ASK, intensity=30, topic_domain=Topic.POLITICS
        )))

        self.assertGreater(session_fav.curiosity, session_bore.curiosity)

    def test_repeated_favorite_topic_decays_curiosity_over_turns(self):
        session = PersonaSession(name="Test", traits={"novelty_drive": 100.0}, expertise_topics=[Topic.POLITICS])
        deltas = []
        prev = session.curiosity
        for _ in range(4):
            session.update(BrainContext(question="q", metadata=make_metadata(
                intent=Intent.ASK, intensity=30, topic_domain=Topic.GENERAL_KNOWLEDGE_FAVORITE
            )))
            deltas.append(session.curiosity - prev)
            prev = session.curiosity

        self.assertTrue(all(d > 0 for d in deltas))
        for earlier, later in zip(deltas, deltas[1:]):
            self.assertGreaterEqual(earlier, later)
        self.assertLess(deltas[-1], deltas[0])

    def test_high_intensity_expertise_claim_spikes_curiosity(self):
        traits = {"novelty_drive": 100.0}

        session_low = PersonaSession(name="Low", traits=traits, expertise_topics=[Topic.POLITICS])
        session_low.update(BrainContext(question="q", metadata=make_metadata(
            intent=Intent.ASK, intensity=30, topic_domain=Topic.POLITICS
        )))

        session_high = PersonaSession(name="High", traits=traits, expertise_topics=[Topic.POLITICS])
        session_high.update(BrainContext(question="q", metadata=make_metadata(
            intent=Intent.ASK, intensity=90, topic_domain=Topic.POLITICS
        )))

        self.assertGreater(session_high.curiosity, session_low.curiosity)

    def test_bridging_directive_for_high_security_low_empathy_persona(self):
        session = PersonaSession(
            name="Bridger",
            traits={"baseline_security": 80.0, "empathic_resonance": 25.0},
            expertise_topics=[Topic.POLITICS],
        )
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.ASK, topic_domain=Topic.SCIENCE))
        session.update(context)
        clause = session.compile_prompt(context)

        self.assertIn("relate or compare it to something in your own areas of expertise", clause)

    def test_honest_teach_me_directive_for_low_security_or_high_empathy_persona(self):
        session = PersonaSession(
            name="Honest",
            traits={"baseline_security": 30.0, "empathic_resonance": 80.0},
            expertise_topics=[Topic.POLITICS],
        )
        context = BrainContext(question="q", metadata=make_metadata(intent=Intent.ASK, topic_domain=Topic.SCIENCE))
        session.update(context)
        clause = session.compile_prompt(context)

        self.assertIn("genuine openness to being taught", clause)
        self.assertNotIn("relate or compare it to something in your own areas of expertise", clause)


if __name__ == "__main__":
    unittest.main()
