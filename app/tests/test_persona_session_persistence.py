import unittest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import cache
from app.database import Base
from app.models import Persona, PersonaSessionModel
from app.persona.persona_session import PersonaSession

# High, unlikely-to-collide ids — persona_service.get_persona_by_id reads
# through the real Redis cache (module-level, shared across test files), so
# distinct ids avoid picking up another test's cached persona rows.
AI_ID = 900001
HUMAN_ID = 900002
AI_ID_2 = 900003
HUMAN_ID_2 = 900004


class TestPersonaSessionPersistence(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()

        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2):
            cache.invalidate_cache(cache.create_persona_key(pid))

        self.ai_persona = Persona(
            id=AI_ID, name="Test AI", desc="", is_human=False, image_url="",
            traits={
                "brain": {
                    "threat_sensitivity": 20.0,
                    "self_regulation": 90.0,
                    "novelty_drive": 60.0,
                    "baseline_security": 70.0,
                    "empathic_resonance": 40.0,
                },
                "interests_expertise": {"expertise": ["cooking", "wine"]},
            },
        )
        self.human_persona = Persona(
            id=HUMAN_ID, name="Test Human", desc="", is_human=True, image_url="",
            traits={
                "identity": {"profession": "Chef", "nationality": "French"},
                "likes_dislikes": {"likes": ["knives"], "dislikes": ["microwaves"]},
            },
            settings={"city": "Lyon"},
        )
        self.ai_persona_2 = Persona(id=AI_ID_2, name="Test AI 2", desc="", is_human=False, image_url="", traits={})
        self.human_persona_2 = Persona(id=HUMAN_ID_2, name="Test Human 2", desc="", is_human=True, image_url="", traits={})

        self.db.add_all([self.ai_persona, self.human_persona, self.ai_persona_2, self.human_persona_2])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2):
            cache.invalidate_cache(cache.create_persona_key(pid))

    async def test_load_with_no_existing_row_returns_baseline_session(self):
        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)

        self.assertIsNone(session.session_id)
        self.assertEqual(session.threat_sensitivity, 20.0)
        self.assertEqual(session.self_regulation, 90.0)
        self.assertEqual(session.expertise_topics, ["cooking", "wine"])
        self.assertIn("Test Human", session.user_info)
        self.assertIn("Chef", session.user_info)
        self.assertIn("Lyon", session.user_info)
        self.assertIn("knives", session.user_info)

    async def test_save_creates_row_then_updates_it(self):
        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        await session.save(self.db)
        first_id = session.session_id
        self.assertIsNotNone(first_id)

        session.arousal = 55.5
        session.turn_count = 3
        await session.save(self.db)

        self.assertEqual(session.session_id, first_id)

        reloaded = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        self.assertEqual(reloaded.session_id, first_id)
        # places=2 rather than the default 7: load() now applies wall-clock
        # decay proportional to elapsed time since last_emotional_update_at,
        # so even the sub-millisecond gap between save() and load() in a
        # fast test run introduces a tiny (~1e-6) but real, expected drift.
        self.assertAlmostEqual(reloaded.arousal, 55.5, places=2)
        self.assertEqual(reloaded.turn_count, 3)

    async def test_load_picks_most_recently_updated_fork(self):
        older = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=10.0, mood=0, rapport=0, curiosity=0,
        )
        newer = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=90.0, patience=90.0, mood=0, rapport=0, curiosity=0,
        )
        self.db.add_all([older, newer])
        await self.db.commit()
        await self.db.refresh(older)
        await self.db.refresh(newer)

        # Force a distinct, later updated_at on `newer` — sqlite's
        # func.now() has second resolution, insertion order alone isn't a
        # reliable ordering signal in a fast test run.
        from sqlalchemy import update
        from datetime import datetime, timedelta, timezone
        await self.db.execute(
            update(PersonaSessionModel).where(PersonaSessionModel.id == newer.id)
            .values(updated_at=datetime.now(timezone.utc) + timedelta(hours=1))
        )
        await self.db.commit()

        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        self.assertEqual(session.session_id, newer.id)
        # places=2 — see test_save_creates_row_then_updates_it for why not 7.
        self.assertAlmostEqual(session.arousal, 90.0, places=2)

    async def test_two_pairs_do_not_cross_contaminate(self):
        session_a = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        session_a.arousal = 77.0
        await session_a.save(self.db)

        session_b = await PersonaSession.load(self.db, AI_ID_2, HUMAN_ID_2)
        session_b.arousal = 12.0
        await session_b.save(self.db)

        reloaded_a = await PersonaSession.load(self.db, AI_ID, HUMAN_ID)
        reloaded_b = await PersonaSession.load(self.db, AI_ID_2, HUMAN_ID_2)

        self.assertNotEqual(reloaded_a.session_id, reloaded_b.session_id)
        # places=2 — see test_save_creates_row_then_updates_it for why not 7.
        self.assertAlmostEqual(reloaded_a.arousal, 77.0, places=2)
        self.assertAlmostEqual(reloaded_b.arousal, 12.0, places=2)


if __name__ == "__main__":
    unittest.main()
