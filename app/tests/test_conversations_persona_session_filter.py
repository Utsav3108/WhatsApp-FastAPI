import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import cache, crud
from app.database import Base
from app.models import Persona, PersonaSessionModel, Message

# High, unlikely-to-collide ids — persona lookups read through the real
# Redis cache (module-level, shared across test files), so distinct ids
# avoid picking up another test's cached rows.
AI_ID = 910001
HUMAN_ID = 910002
OTHER_USER_ID = 910003


class TestConversationsPersonaSessionFilter(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()

        for pid in (AI_ID, HUMAN_ID, OTHER_USER_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

        self.db.add_all([
            Persona(id=AI_ID, name="Fork Test AI", desc="", is_human=False, image_url="", traits={}),
            Persona(id=HUMAN_ID, name="Fork Test Human", desc="", is_human=True, image_url="", traits={}),
            Persona(id=OTHER_USER_ID, name="Other User", desc="", is_human=True, image_url="", traits={}),
        ])
        await self.db.commit()

        self.fork_a = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=0.0, patience=50.0, mood=0.0, rapport=0.0, curiosity=0.0,
        )
        self.fork_b = PersonaSessionModel(
            ai_persona_id=AI_ID, human_persona_id=HUMAN_ID,
            arousal=0.0, patience=50.0, mood=0.0, rapport=0.0, curiosity=0.0,
        )
        self.db.add_all([self.fork_a, self.fork_b])
        await self.db.commit()
        await self.db.refresh(self.fork_a)
        await self.db.refresh(self.fork_b)

        # Three messages in fork A, one in fork B. Explicit, distinct
        # timestamps — inserting all rows in one commit can otherwise tie
        # on the column default's clock resolution, making DESC-ordering
        # (and therefore pagination) nondeterministic.
        base_time = datetime.now(timezone.utc)
        self.db.add_all([
            Message(sender_id=HUMAN_ID, receiver_id=AI_ID, text="a1", persona_session_id=self.fork_a.id,
                    timestamp=base_time),
            Message(sender_id=AI_ID, receiver_id=HUMAN_ID, text="a2", persona_session_id=self.fork_a.id,
                    timestamp=base_time + timedelta(seconds=1)),
            Message(sender_id=HUMAN_ID, receiver_id=AI_ID, text="a3", persona_session_id=self.fork_a.id,
                    timestamp=base_time + timedelta(seconds=2)),
            Message(sender_id=HUMAN_ID, receiver_id=AI_ID, text="b1", persona_session_id=self.fork_b.id,
                    timestamp=base_time),
        ])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        for pid in (AI_ID, HUMAN_ID, OTHER_USER_ID):
            cache.invalidate_cache(cache.create_persona_key(pid))

    async def test_paginated_filter_returns_only_that_forks_messages(self):
        messages, total_count = await crud.get_messages_paginated_by_persona_session_id(
            self.db, persona_session_id=self.fork_a.id, requesting_user_id=HUMAN_ID,
        )
        self.assertEqual(total_count, 3)
        self.assertEqual([m.text for m in messages], ["a1", "a2", "a3"])  # chronological order

        messages_b, total_count_b = await crud.get_messages_paginated_by_persona_session_id(
            self.db, persona_session_id=self.fork_b.id, requesting_user_id=HUMAN_ID,
        )
        self.assertEqual(total_count_b, 1)
        self.assertEqual([m.text for m in messages_b], ["b1"])

    async def test_paginated_filter_respects_pagination(self):
        # Pagination is most-recent-first (same convention as the sibling
        # challenge_session_id function): page 1 is the newest page_size
        # messages, offset walking backwards from there — each page is
        # still returned in chronological order internally.
        page1, total_count = await crud.get_messages_paginated_by_persona_session_id(
            self.db, persona_session_id=self.fork_a.id, requesting_user_id=HUMAN_ID,
            page=1, page_size=2,
        )
        self.assertEqual(total_count, 3)
        self.assertEqual([m.text for m in page1], ["a2", "a3"])

        page2, _ = await crud.get_messages_paginated_by_persona_session_id(
            self.db, persona_session_id=self.fork_a.id, requesting_user_id=HUMAN_ID,
            page=2, page_size=2,
        )
        self.assertEqual([m.text for m in page2], ["a1"])

    async def test_paginated_filter_denies_non_participant(self):
        messages, total_count = await crud.get_messages_paginated_by_persona_session_id(
            self.db, persona_session_id=self.fork_a.id, requesting_user_id=OTHER_USER_ID,
        )
        self.assertEqual(total_count, 0)
        self.assertEqual(messages, [])

    async def test_limit_only_variant_scoped_to_fork(self):
        messages = await crud.get_messages_by_persona_session_id(self.db, self.fork_a.id)
        self.assertEqual([m.text for m in messages], ["a1", "a2", "a3"])

        messages_b = await crud.get_messages_by_persona_session_id(self.db, self.fork_b.id)
        self.assertEqual([m.text for m in messages_b], ["b1"])

    async def test_limit_only_variant_respects_limit(self):
        messages = await crud.get_messages_by_persona_session_id(self.db, self.fork_a.id, limit=2)
        # limit applies to the DESC-ordered query before re-reversing to
        # chronological order, so this returns the most recent 2, in order.
        self.assertEqual([m.text for m in messages], ["a2", "a3"])


if __name__ == "__main__":
    unittest.main()
