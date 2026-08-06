import unittest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi import HTTPException

from app import cache
from app.database import Base
from app.models import Persona, PersonaSessionModel, AdminAuditLog
from app.admin import admin_auth, persona_session_admin_service as ps_service

# High, unlikely-to-collide ids — persona lookups read through the real
# Redis cache (module-level, shared across test files), so distinct ids
# avoid picking up another test's cached rows.
AI_ID = 910001
HUMAN_ID = 910002
AI_ID_2 = 910003
HUMAN_ID_2 = 910004
ADMIN_ID = 910005
NON_ADMIN_ID = 910006


class TestAdminPersonaSessions(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()

        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2, ADMIN_ID, NON_ADMIN_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

        self.ai_persona = Persona(id=AI_ID, name="Admin Test AI", desc="", is_human=False, image_url="", traits={})
        self.human_persona = Persona(id=HUMAN_ID, name="Admin Test Human", desc="", is_human=True, image_url="", traits={})
        self.ai_persona_2 = Persona(id=AI_ID_2, name="Admin Test AI 2", desc="", is_human=False, image_url="", traits={})
        self.human_persona_2 = Persona(id=HUMAN_ID_2, name="Admin Test Human 2", desc="", is_human=True, image_url="", traits={})
        self.admin_persona = Persona(id=ADMIN_ID, name="Admin", desc="", is_human=True, image_url="", traits={}, is_admin=True)
        self.non_admin_persona = Persona(id=NON_ADMIN_ID, name="Regular User", desc="", is_human=True, image_url="", traits={}, is_admin=False)

        self.db.add_all([
            self.ai_persona, self.human_persona, self.ai_persona_2, self.human_persona_2,
            self.admin_persona, self.non_admin_persona,
        ])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        for pid in (AI_ID, HUMAN_ID, AI_ID_2, HUMAN_ID_2, ADMIN_ID, NON_ADMIN_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

    async def test_get_current_admin_user_allows_admin(self):
        result = await admin_auth.get_current_admin_user(current_user=self.admin_persona)
        self.assertEqual(result.id, ADMIN_ID)

    async def test_get_current_admin_user_rejects_non_admin(self):
        with self.assertRaises(HTTPException) as ctx:
            await admin_auth.get_current_admin_user(current_user=self.non_admin_persona)
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_reset_block_idempotent_on_already_unblocked_session(self):
        session = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=90.0, mood=0, rapport=0, curiosity=0,
            is_blocked=False, block_reason=None, violation_count=0,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        result = await ps_service.reset_block(self.db, session.id, admin_id=ADMIN_ID)
        self.assertIsNotNone(result)
        self.assertFalse(result.is_blocked)
        self.assertIsNone(result.block_reason)
        self.assertEqual(result.violation_count, 0)

        # Audit row still written even though nothing materially changed.
        logs = (await self.db.execute(
            select(AdminAuditLog).filter(AdminAuditLog.target_id == str(session.id))
        )).scalars().all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].admin_id, ADMIN_ID)
        self.assertEqual(logs[0].action, "reset_block")

    async def test_reset_block_clears_blocked_state(self):
        session = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=95.0, patience=5.0, mood=-50, rapport=0, curiosity=0,
            is_blocked=True, block_reason="repeated_content_violations", violation_count=3,
            blocked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        result = await ps_service.reset_block(self.db, session.id, admin_id=ADMIN_ID)
        self.assertFalse(result.is_blocked)
        self.assertIsNone(result.block_reason)
        self.assertIsNone(result.blocked_until)
        self.assertEqual(result.violation_count, 0)

    async def test_reset_block_missing_session_returns_none(self):
        result = await ps_service.reset_block(self.db, 999999, admin_id=ADMIN_ID)
        self.assertIsNone(result)

    async def test_fork_disambiguation_in_listing_and_detail(self):
        fork_a = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=90.0, mood=0, rapport=0, curiosity=0,
            is_blocked=False,
        )
        fork_b = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=95.0, patience=5.0, mood=0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="repeated_content_violations",
            blocked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        self.db.add_all([fork_a, fork_b])
        await self.db.commit()
        await self.db.refresh(fork_a)
        await self.db.refresh(fork_b)

        pairs = await ps_service.list_pairs(self.db, ai_persona_id=AI_ID, human_persona_id=HUMAN_ID)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].fork_count, 2)
        self.assertTrue(pairs[0].any_fork_blocked)

        forks = await ps_service.get_forks(self.db, AI_ID, HUMAN_ID)
        self.assertEqual({f.id for f in forks}, {fork_a.id, fork_b.id})

        detail_a = await ps_service.get_detail(self.db, fork_a.id)
        detail_b = await ps_service.get_detail(self.db, fork_b.id)
        self.assertEqual(detail_a.id, fork_a.id)
        self.assertFalse(detail_a.is_blocked)
        self.assertEqual(detail_b.id, fork_b.id)
        self.assertTrue(detail_b.is_blocked)

    async def test_has_blocked_fork_filter(self):
        # Pair (AI_ID, HUMAN_ID): one blocked fork.
        blocked_fork = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=95.0, patience=5.0, mood=0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="repeated_content_violations",
            blocked_until=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        # Pair (AI_ID_2, HUMAN_ID_2): no blocked forks.
        unblocked_fork = PersonaSessionModel(
            ai_persona_id=AI_ID_2, human_persona_id=HUMAN_ID_2,
            arousal=10.0, patience=90.0, mood=0, rapport=0, curiosity=0,
            is_blocked=False,
        )
        self.db.add_all([blocked_fork, unblocked_fork])
        await self.db.commit()

        blocked_pairs = await ps_service.list_pairs(self.db, has_blocked_fork=True)
        self.assertEqual(len(blocked_pairs), 1)
        self.assertEqual(blocked_pairs[0].ai_persona_id, AI_ID)

        unblocked_pairs = await ps_service.list_pairs(self.db, has_blocked_fork=False)
        self.assertEqual(len(unblocked_pairs), 1)
        self.assertEqual(unblocked_pairs[0].ai_persona_id, AI_ID_2)

    async def test_get_detail_includes_linked_message_count(self):
        from app.models import Message

        session = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=10.0, patience=90.0, mood=0, rapport=0, curiosity=0,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        self.db.add_all([
            Message(sender_id=HUMAN_ID, receiver_id=AI_ID, text="hi", persona_session_id=session.id),
            Message(sender_id=AI_ID, receiver_id=HUMAN_ID, text="hello", persona_session_id=session.id),
        ])
        await self.db.commit()

        detail = await ps_service.get_detail(self.db, session.id)
        self.assertEqual(detail.linked_message_count, 2)

    async def test_stale_is_blocked_column_reported_as_unblocked(self):
        # is_blocked=True is stale here (the column is only refreshed by
        # PersonaSession.load()'s lazy-unblock path, which admin reads never
        # go through) — blocked_until has already passed, so admin-facing
        # reads must report this as NOT blocked.
        session = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=50.0, patience=50.0, mood=0, rapport=0, curiosity=0,
            is_blocked=True, block_reason="arousal_threshold",
            blocked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        pairs = await ps_service.list_pairs(self.db, ai_persona_id=AI_ID, human_persona_id=HUMAN_ID)
        self.assertEqual(len(pairs), 1)
        self.assertFalse(pairs[0].any_fork_blocked)

        forks = await ps_service.get_forks(self.db, AI_ID, HUMAN_ID)
        self.assertFalse(forks[0].is_blocked)

        detail = await ps_service.get_detail(self.db, session.id)
        self.assertFalse(detail.is_blocked)


if __name__ == "__main__":
    unittest.main()
