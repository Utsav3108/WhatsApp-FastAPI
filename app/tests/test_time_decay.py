import math
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import cache
from app.database import Base
from app.models import Persona, PersonaSessionModel
from app.brain.emotion_engine import EmotionEngine
from app.brain.schemas import Intent, Tone, Topic, UserMessageMetaDataResponse
from app.brain.context import BrainContext
from app.persona import persona_session_crud
from app.persona.persona_session import PersonaSession
import app.persona.persona_session as persona_session_module

# High, unlikely-to-collide ids — persona lookups read through the real
# Redis cache (module-level, shared across test files), so distinct ids
# avoid picking up another test's cached rows.
AI_ID = 930001
HUMAN_ID = 930002

# Chosen so half_life_hours() gives a clean, moderate cooldown window
# (24 hours) rather than something near-instant or near-permanent.
BRAIN_TRAITS = {
    "threat_sensitivity": 90.0,
    "self_regulation": 90.0,
    "novelty_drive": 50.0,
    "baseline_security": 60.0,
    "empathic_resonance": 50.0,
}


def make_metadata(intent=Intent.CONVERSATION, tone=Tone.NEUTRAL, intensity=30,
                   topic_domain=Topic.GENERAL_KNOWLEDGE_FAVORITE, language="en") -> UserMessageMetaDataResponse:
    return UserMessageMetaDataResponse(
        intent=intent, tone=tone, intensity=intensity, topic_domain=topic_domain, language=language
    )


class TestTimeDecayMath(unittest.TestCase):
    """Pure in-memory tests — no DB/Redis needed, same style as
    test_competition_arousal_fix.py."""

    def test_arousal_threshold_sets_blocked_until_and_is_blocked(self):
        session = PersonaSession(name="Test", traits=BRAIN_TRAITS)
        session.arousal = session.BLOCK_THRESHOLD

        before = datetime.now(timezone.utc)
        context = BrainContext(question="q", metadata=make_metadata())
        session.compile_prompt(context)
        after = datetime.now(timezone.utc)

        self.assertTrue(session.is_blocked)
        self.assertEqual(session.block_reason, "arousal_threshold")
        self.assertTrue(session.just_blocked)
        self.assertIsNotNone(session.blocked_until)
        self.assertGreaterEqual(
            session.blocked_until, before + timedelta(hours=persona_session_module.BLOCK_DURATION_HOURS)
        )
        self.assertLessEqual(
            session.blocked_until, after + timedelta(hours=persona_session_module.BLOCK_DURATION_HOURS)
        )

    def test_just_blocked_does_not_refire_on_next_turn(self):
        session = PersonaSession(name="Test", traits=BRAIN_TRAITS)
        session.arousal = session.BLOCK_THRESHOLD
        context = BrainContext(question="q", metadata=make_metadata())
        session.compile_prompt(context)
        self.assertTrue(session.just_blocked)

        # A second turn: update() resets just_blocked at the top, and the
        # hard is_blocked gate at the top of compile_prompt() short-circuits
        # before the arousal-threshold branch could ever re-set it.
        session.update(context)
        self.assertFalse(session.just_blocked)
        session.compile_prompt(context)
        self.assertFalse(session.just_blocked)

    def test_violation_count_sets_blocked_until_and_is_blocked(self):
        session = PersonaSession(name="Test", traits=BRAIN_TRAITS, violation_block_threshold=2)

        before = datetime.now(timezone.utc)
        session.register_violation(Topic.NUDITY)
        self.assertFalse(session.is_blocked)  # first violation, threshold not yet reached
        self.assertFalse(session.just_blocked)
        session.register_violation(Topic.NUDITY)
        after = datetime.now(timezone.utc)

        self.assertTrue(session.is_blocked)
        self.assertEqual(session.block_reason, "repeated_content_violations")
        self.assertTrue(session.just_blocked)
        self.assertIsNotNone(session.blocked_until)
        self.assertGreaterEqual(
            session.blocked_until, before + timedelta(hours=persona_session_module.BLOCK_DURATION_HOURS)
        )
        self.assertLessEqual(
            session.blocked_until, after + timedelta(hours=persona_session_module.BLOCK_DURATION_HOURS)
        )

    def test_register_violation_does_not_reset_just_blocked_once_already_blocked(self):
        session = PersonaSession(name="Test", traits=BRAIN_TRAITS, violation_block_threshold=1)
        session.register_violation(Topic.NUDITY)
        self.assertTrue(session.is_blocked)
        self.assertTrue(session.just_blocked)

        # Simulate a fresh turn's reset (as update() would do), then another
        # violation while already blocked — must NOT re-set just_blocked.
        session.just_blocked = False
        session.register_violation(Topic.NUDITY)
        self.assertTrue(session.is_blocked)
        self.assertFalse(session.just_blocked)

    def test_block_duration_constant_is_single_source_of_truth(self):
        with patch.object(persona_session_module, "BLOCK_DURATION_HOURS", 3.0):
            session = PersonaSession(name="Test", traits=BRAIN_TRAITS, violation_block_threshold=1)
            before = datetime.now(timezone.utc)
            session.register_violation(Topic.NUDITY)
            after = datetime.now(timezone.utc)

            self.assertGreaterEqual(session.blocked_until, before + timedelta(hours=3.0))
            self.assertLessEqual(session.blocked_until, after + timedelta(hours=3.0))
            # Not the default 1.0-hour duration.
            self.assertGreater(session.blocked_until, before + timedelta(hours=1.5))


class TestTimeDecayPersistence(unittest.IsolatedAsyncioTestCase):
    """DB-backed tests — same SQLite in-memory setup as
    test_persona_session_persistence.py."""

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()

        for pid in (AI_ID, HUMAN_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

        self.ai_persona = Persona(
            id=AI_ID, name="Decay Test AI", desc="", is_human=False, image_url="",
            traits={"brain": BRAIN_TRAITS},
        )
        self.human_persona = Persona(id=HUMAN_ID, name="Decay Test Human", desc="", is_human=True, image_url="", traits={})

        self.db.add_all([self.ai_persona, self.human_persona])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        for pid in (AI_ID, HUMAN_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

    async def test_decay_matches_hand_computed_value(self):
        elapsed_hours = 10.0
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=90.0, patience=50.0, mood=50.0, rapport=30.0, curiosity=20.0,
            last_emotional_update_at=datetime.now(timezone.utc) - timedelta(hours=elapsed_hours),
        )
        self.db.add(row)
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)

        expected_deltas = EmotionEngine.time_cooldown_delta(
            arousal=90.0, mood=50.0, patience=50.0,
            self_regulation=BRAIN_TRAITS["self_regulation"],
            threat_sensitivity=BRAIN_TRAITS["threat_sensitivity"],
            baseline_security=BRAIN_TRAITS["baseline_security"],
            elapsed_hours=elapsed_hours,
        )
        self.assertAlmostEqual(session.arousal, 90.0 + expected_deltas["arousal"], places=2)
        self.assertAlmostEqual(session.mood, 50.0 + expected_deltas["mood"], places=2)
        self.assertAlmostEqual(session.patience, 50.0 + expected_deltas["patience"], places=2)
        # Sanity: decay actually did something, this isn't a no-op fixture.
        self.assertLess(session.arousal, 90.0)

    async def test_rapport_unaffected_by_time_decay(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=90.0, patience=50.0, mood=50.0, rapport=42.0, curiosity=20.0,
            last_emotional_update_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        self.db.add(row)
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        self.assertEqual(session.rapport, 42.0)

    async def test_load_freezes_state_while_still_blocked(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=100.0, patience=50.0, mood=50.0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="arousal_threshold",
            blocked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
            last_emotional_update_at=datetime.now(timezone.utc) - timedelta(hours=10),
        )
        self.db.add(row)
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        self.assertTrue(session.is_blocked)
        self.assertEqual(session.arousal, 100.0)  # unchanged, no partial decay

    async def test_load_auto_unblocks_and_decays_together(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=100.0, patience=50.0, mood=50.0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="repeated_content_violations",
            blocked_until=datetime.now(timezone.utc) - timedelta(seconds=1),
            last_emotional_update_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=5),
        )
        self.db.add(row)
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)

        self.assertFalse(session.is_blocked)
        self.assertIsNone(session.blocked_until)
        # Decayed from 100, not left at 100 and not reset to __init__'s
        # baseline formula value (max(0, 30 - baseline_security/4) = 15.0
        # for baseline_security=60 — a much lower number that would
        # indicate a bug resetting to defaults instead of decaying).
        self.assertLess(session.arousal, 100.0)
        self.assertGreater(session.arousal, 50.0)

    async def test_hard_gate_save_does_not_bump_decay_anchor(self):
        anchor_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        old_updated_at = datetime.now(timezone.utc) - timedelta(days=1)

        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=100.0, patience=10.0, mood=-50.0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="arousal_threshold",
            blocked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
            last_emotional_update_at=anchor_time,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        # Force updated_at to a known-old value (explicit .values() bypasses
        # onupdate, same technique used in test_persona_session_persistence.py).
        await self.db.execute(
            sa_update(PersonaSessionModel).where(PersonaSessionModel.id == row.id)
            .values(updated_at=old_updated_at)
        )
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        self.assertTrue(session.is_blocked)  # still frozen/blocked

        await session.save(self.db, state_changed=False)

        reloaded_row = await persona_session_crud.get_persona_session_by_id(self.db, row.id)
        # update_persona_session()'s raw UPDATE deliberately excludes
        # updated_at (so the DB's onupdate=func.now() fires), which makes
        # the ORM auto-expire that attribute on the already-identity-mapped
        # object — refresh explicitly so the next access doesn't attempt a
        # lazy (sync-context) reload under AsyncSession.
        await self.db.refresh(reloaded_row)
        self.assertEqual(
            reloaded_row.last_emotional_update_at.replace(tzinfo=None),
            anchor_time.replace(tzinfo=None),
        )
        # updated_at bumped despite state_changed=False, via the DB's
        # onupdate=func.now() — unrelated to last_emotional_update_at.
        self.assertNotEqual(
            reloaded_row.updated_at.replace(tzinfo=None),
            old_updated_at.replace(tzinfo=None),
        )


if __name__ == "__main__":
    unittest.main()
