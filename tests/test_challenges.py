import unittest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base
from app.models import Challenge, ChallengeAttempt, ChallengeSession, Persona
from app.crud import (
    get_daily_challenge,
    get_trending_challenges,
    get_recommended_challenges,
    get_recently_added_challenges
)

class TestChallengesDashboard(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # 1. Setup in-memory SQLite database
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)
        
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        self.db = self.SessionLocal()
        await self.seed_data()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def seed_data(self):
        # 2. Seed mock personas
        self.user1 = Persona(id=1, name="User One", desc="", traits="Friendly", image_url="")
        self.user2 = Persona(id=2, name="User Two", desc="", traits="Friendly", image_url="")
        self.persona3 = Persona(id=3, name="Opponent Three", desc="", traits="Friendly", image_url="")
        
        self.db.add_all([self.user1, self.user2, self.persona3])
        await self.db.flush()

        # 3. Seed mock challenges
        # Challenge A: created 72 hours ago
        self.challenge_a = Challenge(
            id="challenge_a",
            title="Challenge A",
            for_user=True,
            created_at=datetime.utcnow() - timedelta(hours=72)
        )
        # Challenge B: created 24 hours ago
        self.challenge_b = Challenge(
            id="challenge_b",
            title="Challenge B",
            for_user=True,
            created_at=datetime.utcnow() - timedelta(hours=24)
        )
        # Challenge C: created 12 hours ago
        self.challenge_c = Challenge(
            id="challenge_c",
            title="Challenge C",
            for_user=True,
            created_at=datetime.utcnow() - timedelta(hours=12)
        )
        # Challenge D: created 1 hour ago, but for_user = False (unpublished)
        self.challenge_d = Challenge(
            id="challenge_d",
            title="Challenge D",
            for_user=False,
            created_at=datetime.utcnow() - timedelta(hours=1)
        )

        self.db.add_all([self.challenge_a, self.challenge_b, self.challenge_c, self.challenge_d])
        await self.db.flush()
        await self.db.commit()

    async def test_daily_challenge(self):
        # Test that daily challenge selects a challenge deterministically
        daily_1 = await get_daily_challenge(self.db)
        daily_2 = await get_daily_challenge(self.db)
        
        # Must be non-null
        self.assertIsNotNone(daily_1)
        # Must be identical for subsequent requests on the same day
        self.assertEqual(daily_1.id, daily_2.id)
        # Must exclude unpublished challenge_d
        self.assertIn(daily_1.id, ["challenge_a", "challenge_b", "challenge_c"])

    async def test_trending_challenges(self):
        # Create active sessions
        # User 2 has active session for Challenge A
        session_a_other = ChallengeSession(
            id=101,
            user_id=self.user2.id,
            challenge_id=self.challenge_a.id,
            persona_id=self.persona3.id,
            status="active"
        )
        # User 2 has active session for Challenge B
        session_b_other = ChallengeSession(
            id=102,
            user_id=self.user2.id,
            challenge_id=self.challenge_b.id,
            persona_id=self.persona3.id,
            status="active"
        )
        # User 1 (current user) has active session for Challenge B
        session_b_self = ChallengeSession(
            id=103,
            user_id=self.user1.id,
            challenge_id=self.challenge_b.id,
            persona_id=self.persona3.id,
            status="active"
        )
        
        self.db.add_all([session_a_other, session_b_other, session_b_self])
        await self.db.commit()

        # Query trending for User 1
        trending = await get_trending_challenges(self.db, current_user_id=self.user1.id)
        
        # Challenge B has 2 active sessions but since current user (user 1) is actively playing it, it must be excluded!
        # Challenge A has 1 active session by user 2, so it should be included.
        # Challenge C has 0 active sessions, so it has count 0.
        
        trending_ids = [c.id for c in trending]
        self.assertIn("challenge_a", trending_ids)
        self.assertNotIn("challenge_b", trending_ids)
        self.assertNotIn("challenge_d", trending_ids) # Excluded as it's not active/for_user

    async def test_recommended_challenges(self):
        # Seed mock attempts:
        # Challenge B gets 5 attempts
        # Challenge A gets 3 attempts
        # Challenge C gets 1 attempt
        attempts = []
        for i in range(5):
            attempts.append(ChallengeAttempt(challenge_session_id=1, challenge_id=self.challenge_b.id, user_id=self.user2.id, persona_id=self.persona3.id, won=True))
        for i in range(3):
            attempts.append(ChallengeAttempt(challenge_session_id=1, challenge_id=self.challenge_a.id, user_id=self.user2.id, persona_id=self.persona3.id, won=True))
        for i in range(1):
            attempts.append(ChallengeAttempt(challenge_session_id=1, challenge_id=self.challenge_c.id, user_id=self.user2.id, persona_id=self.persona3.id, won=True))
            
        self.db.add_all(attempts)
        await self.db.commit()

        recommended = await get_recommended_challenges(self.db)
        recommended_ids = [c.id for c in recommended]
        
        # Must be ordered by attempts descending: B, A, C
        self.assertEqual(recommended_ids[:3], ["challenge_b", "challenge_a", "challenge_c"])
        # Should not include challenge_d (for_user = False)
        self.assertNotIn("challenge_d", recommended_ids)

    async def test_recently_added_challenges(self):
        recently_added = await get_recently_added_challenges(self.db)
        recently_added_ids = [c.id for c in recently_added]
        
        # Challenge B (created 24h ago) and Challenge C (created 12h ago) match the <48h window.
        # Challenge A (created 72h ago) is excluded.
        # Challenge D (for_user = False) is excluded.
        # Must be ordered newest first: Challenge C, then Challenge B.
        self.assertEqual(recently_added_ids, ["challenge_c", "challenge_b"])

    async def test_completed_daily_challenge_not_in_dashboard(self):
        from app.services.challenge_service import get_challenges_dashboard
        
        # 1. Fetch dashboard without completed attempts - daily challenge should be present
        dashboard_before = await get_challenges_dashboard(self.db, current_user_id=self.user1.id)
        self.assertIsNotNone(dashboard_before.daily_challenge)
        daily_id = dashboard_before.daily_challenge.id
        
        # 2. Add a won (completed) attempt for user1
        completed_attempt = ChallengeAttempt(
            challenge_session_id=201,
            challenge_id=daily_id,
            user_id=self.user1.id,
            persona_id=self.persona3.id,
            won=True
        )
        self.db.add(completed_attempt)
        await self.db.commit()
        
        # 3. Fetch dashboard for user1 - daily challenge should now be None
        dashboard_after = await get_challenges_dashboard(self.db, current_user_id=self.user1.id)
        self.assertIsNone(dashboard_after.daily_challenge)
        
        # 4. Fetch dashboard for user2 (no completed attempts) - daily challenge should still be present
        dashboard_other = await get_challenges_dashboard(self.db, current_user_id=self.user2.id)
        self.assertIsNotNone(dashboard_other.daily_challenge)
        self.assertEqual(dashboard_other.daily_challenge.id, daily_id)

    async def test_challenge_session_timer(self):
        from app.services.challenge_session import setup_challenge_session
        from app.schemas import ChallengeSetup
        
        # Setup challenge session
        req = ChallengeSetup(
            challenge_id=self.challenge_b.id,
            persona_id=self.persona3.id,
            user_id=self.user1.id
        )
        resp = await setup_challenge_session(self.db, req)
        self.assertIsNotNone(resp.challenge_session_id)
        self.assertEqual(resp.elapsed_seconds, 0)
        
        session = await self.db.get(ChallengeSession, resp.challenge_session_id)
        self.assertIsNotNone(session.last_resumed_at)
        
        # Simulate elapsed time of 30 seconds
        session.last_resumed_at = datetime.utcnow() - timedelta(seconds=30)
        await self.db.commit()
        
        # Simulate pause logic
        now = datetime.utcnow()
        delta = (now - session.last_resumed_at.replace(tzinfo=None)).total_seconds()
        session.elapsed_seconds += int(delta)
        session.last_resumed_at = None
        await self.db.commit()
        
        self.assertGreaterEqual(session.elapsed_seconds, 30)
        self.assertIsNone(session.last_resumed_at)
        
        # Resume the session again for a final 15-second segment
        session.last_resumed_at = datetime.utcnow() - timedelta(seconds=15)
        session.status = 'active'
        await self.db.commit()
        
        # Complete the session
        from app.services.challenge_session import complete_challenge_session
        from app.schemas import ChallengeCompletion
        completion_req = ChallengeCompletion(
            challenge_session_id=session.id,
            challenge_status="won",
            reason="Completed successfully",
            user_id=self.user1.id,
            challenge_id=self.challenge_b.id
        )
        await complete_challenge_session(self.db, completion_req)
        
        # Verify that the created ChallengeAttempt has the correct time_taken_seconds (30 + 15 = 45 seconds)
        from app.models import ChallengeAttempt
        from sqlalchemy import select
        stmt = select(ChallengeAttempt).filter(ChallengeAttempt.challenge_session_id == session.id)
        attempt = (await self.db.execute(stmt)).scalars().first()
        self.assertIsNotNone(attempt)
        self.assertGreaterEqual(attempt.time_taken_seconds, 44)
        self.assertLessEqual(attempt.time_taken_seconds, 48)

if __name__ == "__main__":
    unittest.main()
