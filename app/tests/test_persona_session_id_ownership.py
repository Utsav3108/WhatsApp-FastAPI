import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import cache
from app.database import Base
from app.models import Persona, PersonaSessionModel
from app.persona import persona_session_crud
from app.persona.persona_session import PersonaSession, PersonaSessionMismatchError

# High, unlikely-to-collide ids — persona_service.get_persona_by_id reads
# through the real Redis cache (module-level, shared across test files), so
# distinct ids avoid picking up another test's cached persona rows.
AI_ID = 900101
HUMAN_ID = 900102
AI_ID_2 = 900103
HUMAN_ID_2 = 900104


class TestPersonaSessionIdOwnership(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()

        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2):
            cache.invalidate_cache(cache.create_persona_key(pid))

        self.ai_persona = Persona(id=AI_ID, name="Test AI", desc="", is_human=False, image_url="", traits={})
        self.human_persona = Persona(id=HUMAN_ID, name="Test Human", desc="", is_human=True, image_url="", traits={})
        self.ai_persona_2 = Persona(id=AI_ID_2, name="Test AI 2", desc="", is_human=False, image_url="", traits={})
        self.human_persona_2 = Persona(id=HUMAN_ID_2, name="Test Human 2", desc="", is_human=True, image_url="", traits={})

        self.db.add_all([self.ai_persona, self.human_persona, self.ai_persona_2, self.human_persona_2])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2):
            cache.invalidate_cache(cache.create_persona_key(pid))

    # --- CRUD layer -------------------------------------------------------

    async def test_get_by_id_for_pair_returns_row_on_match(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=10.0, mood=0, rapport=0, curiosity=0,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        fetched = await persona_session_crud.get_persona_session_by_id_for_pair(
            self.db, row.id, AI_ID, HUMAN_ID
        )
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, row.id)

    async def test_get_by_id_for_pair_returns_none_on_wrong_pair(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=10.0, mood=0, rapport=0, curiosity=0,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        fetched = await persona_session_crud.get_persona_session_by_id_for_pair(
            self.db, row.id, AI_ID_2, HUMAN_ID_2
        )
        self.assertIsNone(fetched)

    async def test_get_by_id_for_pair_returns_none_on_nonexistent_id(self):
        fetched = await persona_session_crud.get_persona_session_by_id_for_pair(
            self.db, 999999999, AI_ID, HUMAN_ID
        )
        self.assertIsNone(fetched)

    # --- PersonaSession.load() ---------------------------------------------

    async def test_load_with_explicit_id_picks_that_fork_not_latest(self):
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

        # Force a distinct, later updated_at on `newer` so it would win a
        # "latest fork" lookup — proves the explicit persona_session_id
        # below overrides that, rather than silently picking newer anyway.
        await self.db.execute(
            update(PersonaSessionModel).where(PersonaSessionModel.id == newer.id)
            .values(updated_at=datetime.now(timezone.utc) + timedelta(hours=1))
        )
        await self.db.commit()

        session = await PersonaSession.load(
            self.db, AI_ID, HUMAN_ID, persona_session_id=older.id
        )
        self.assertEqual(session.session_id, older.id)
        self.assertAlmostEqual(session.arousal, 10.0, places=2)

    async def test_load_with_mismatched_pair_raises(self):
        row = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=10.0, mood=0, rapport=0, curiosity=0,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        with self.assertRaises(PersonaSessionMismatchError):
            await PersonaSession.load(
                self.db, AI_ID_2, HUMAN_ID_2, persona_session_id=row.id
            )

    async def test_load_with_nonexistent_id_raises(self):
        with self.assertRaises(PersonaSessionMismatchError):
            await PersonaSession.load(
                self.db, AI_ID, HUMAN_ID, persona_session_id=999999999
            )

    async def test_load_without_id_still_falls_back_to_latest(self):
        session = await PersonaSession.load(self.db, AI_ID, HUMAN_ID, persona_session_id=None)
        self.assertIsNone(session.session_id)


if __name__ == "__main__":
    unittest.main()
