import unittest
import asyncio
from datetime import datetime, timedelta, timezone
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
        self.user1 = Persona(id=1, name="User One", desc="", traits="Friendly", image_url="", is_human=True)
        self.user2 = Persona(id=2, name="User Two", desc="", traits="Friendly", image_url="", is_human=True)
        self.persona3 = Persona(id=3, name="Opponent Three", desc="", traits="Friendly", image_url="", is_human=False)
        
        self.db.add_all([self.user1, self.user2, self.persona3])
        await self.db.flush()

        # 3. Seed mock challenges
        # Challenge A: created 72 hours ago
        self.challenge_a = Challenge(
            id="challenge_a",
            title="Challenge A",
            for_user=True,
            created_at=datetime.now(timezone.utc) - timedelta(hours=72)
        )
        # Challenge B: created 23 hours ago
        self.challenge_b = Challenge(
            id="challenge_b",
            title="Challenge B",
            for_user=True,
            created_at=datetime.now(timezone.utc) - timedelta(hours=23)
        )
        # Challenge C: created 12 hours ago
        self.challenge_c = Challenge(
            id="challenge_c",
            title="Challenge C",
            for_user=True,
            created_at=datetime.now(timezone.utc) - timedelta(hours=12)
        )
        # Challenge D: created 1 hour ago, but for_user = False (unpublished)
        self.challenge_d = Challenge(
            id="challenge_d",
            title="Challenge D",
            for_user=False,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1)
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
        
        # Challenge B (created 23h ago) and Challenge C (created 12h ago) match the <24h window.
        # Challenge A (created 72h ago) is excluded.
        # Challenge D (for_user = False) is excluded.
        # Must be ordered newest first: Challenge C, then Challenge B.
        self.assertEqual(recently_added_ids, ["challenge_c", "challenge_b"])

        # Create an attempt for user1 on challenge_b
        from app.models import ChallengeAttempt
        from app.enums import ChallengeResult
        attempt = ChallengeAttempt(
            challenge_session_id=1,
            challenge_id="challenge_b",
            user_id=self.user1.id,
            persona_id=self.persona3.id,
            won=True,
            time_taken_seconds=30
        )
        self.db.add(attempt)
        await self.db.flush()
        await self.db.commit()

        # Query recently added passing user1's id
        recently_added_for_user = await get_recently_added_challenges(self.db, user_id=self.user1.id)
        recently_added_user_ids = [c.id for c in recently_added_for_user]

        # challenge_b should be excluded now because user1 has attempted it
        self.assertEqual(recently_added_user_ids, ["challenge_c"])

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
        session.last_resumed_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        await self.db.commit()
        
        # Simulate pause logic
        now = datetime.now(timezone.utc)
        delta = (now - session.last_resumed_at).total_seconds()
        session.elapsed_seconds += int(delta)
        session.last_resumed_at = None
        await self.db.commit()
        
        self.assertGreaterEqual(session.elapsed_seconds, 30)
        self.assertIsNone(session.last_resumed_at)
        
        # Resume the session again for a final 15-second segment
        session.last_resumed_at = datetime.now(timezone.utc) - timedelta(seconds=15)
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

    async def test_first_message_from_persona(self):
        # 1. Create a challenge with first_message_from_persona = True
        from app.models import ChallengeContext
        challenge_e = Challenge(
            id="challenge_e",
            title="Challenge E",
            for_user=True,
            first_message_from_persona=True,
            created_at=datetime.now(timezone.utc),
            selected_persona_id=self.persona3.id
        )
        context_e = ChallengeContext(
            challenge_id="challenge_e",
            setting="A quiet trailer",
            goal="Get the date",
            platform="Chat",
            stakes="None"
        )
        self.db.add(challenge_e)
        self.db.add(context_e)
        await self.db.flush()
        await self.db.commit()

        # 2. Mock ask_gemini call to avoid real API hit during tests
        from unittest.mock import patch
        from app.schemas import MessageCreate, ChallengeSetup

        mock_msg = MessageCreate(
            sender_id=self.persona3.id,
            receiver_id=self.user1.id,
            text="Hello user, welcome to my challenge!",
            challenge_session_id=1
        )

        with patch("app.gemini.ask_gemini", return_value=mock_msg) as mock_ask:
            req = ChallengeSetup(
                challenge_id="challenge_e",
                user_id=self.user1.id
            )
            from app.services.challenge_session import setup_challenge_session
            resp = await setup_challenge_session(self.db, req)
            
            # Verify mock was called
            mock_ask.assert_called_once()
            
            # Verify the response structure
            self.assertIsNotNone(resp.challenge_session_id)
            
            from app.crud import get_messages_by_challenge_session_id
            db_messages = await get_messages_by_challenge_session_id(self.db, resp.challenge_session_id)
            self.assertEqual(len(db_messages), 1)
            self.assertEqual(db_messages[0].text, "Hello user, welcome to my challenge!")
            self.assertEqual(db_messages[0].sender_id, self.persona3.id)
            self.assertEqual(db_messages[0].receiver_id, self.user1.id)

    async def test_personas_filtering_non_human_only(self):
        from app.crud import get_all_personas, search_personas
        
        # get_all_personas should only return non-human personas (persona3)
        all_personas = await get_all_personas(self.db)
        persona_ids = [p.id for p in all_personas]
        self.assertIn(self.persona3.id, persona_ids)
        self.assertNotIn(self.user1.id, persona_ids)
        self.assertNotIn(self.user2.id, persona_ids)

        # search_personas should only return non-human personas
        searched = await search_personas(self.db, query="User")
        self.assertEqual(len(searched), 0)

        searched_opponent = await search_personas(self.db, query="Opponent")
        self.assertEqual(len(searched_opponent), 1)
        self.assertEqual(searched_opponent[0].id, self.persona3.id)

    async def test_upsert_challenges_validation(self):
        from app.crud import upsert_challenges
        from app.schemas import ChallengeCreate, ChallengeContextCreate
        
        ctx = ChallengeContextCreate(
            setting="trailer",
            goal="get date",
            stakes="none",
            platform="chat"
        )
        
        # Test validation for selected_persona_id
        challenge_invalid_selected = ChallengeCreate(
            id="challenge_invalid_selected",
            title="Invalid Selected",
            context=ctx,
            selected_persona_id=self.user1.id  # human user
        )
        with self.assertRaises(ValueError) as context:
            await upsert_challenges(self.db, challenge_invalid_selected)
        self.assertIn("Selected persona for challenge cannot be a human user", str(context.exception))

        # Test validation for suggested_personas
        challenge_invalid_suggested = ChallengeCreate(
            id="challenge_invalid_suggested",
            title="Invalid Suggested",
            context=ctx,
            suggested_personas=[self.persona3.id, self.user2.id]  # user2 is human
        )
        with self.assertRaises(ValueError) as context:
            await upsert_challenges(self.db, challenge_invalid_suggested)
        self.assertIn("Suggested personas for challenge cannot include human users", str(context.exception))

        # Test success case
        challenge_valid = ChallengeCreate(
            id="challenge_valid",
            title="Valid Challenge",
            context=ctx,
            selected_persona_id=self.persona3.id,
            suggested_personas=[self.persona3.id]
        )
        res = await upsert_challenges(self.db, challenge_valid)
        self.assertIsNotNone(res)

    async def test_create_challenge_api_validation(self):
        from app.routers.challenge import create_challenge
        from app.schemas import ChallengeCreate, ChallengeContextCreate
        from fastapi import HTTPException

        ctx = ChallengeContextCreate(
            setting="trailer",
            goal="get date",
            stakes="none",
            platform="chat"
        )

        # Test router catches ValueError and raises HTTPException(400)
        challenge_invalid = ChallengeCreate(
            id="challenge_invalid_api",
            title="Invalid API Challenge",
            context=ctx,
            selected_persona_id=self.user1.id  # human user
        )
        with self.assertRaises(HTTPException) as context:
            await create_challenge(challenge_invalid, self.db)
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Selected persona for challenge cannot be a human user", context.exception.detail)

    async def test_challenge_attempt_difficulty_logging(self):
        # Create a challenge with difficulty = 'advance'
        from app.models import ChallengeContext
        challenge_adv = Challenge(
            id="challenge_adv",
            title="Challenge Advanced Difficulty",
            difficulty="advance",
            for_user=True,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(challenge_adv)
        await self.db.commit()
        
        # Start session
        from app.services.challenge_session import setup_challenge_session
        from app.schemas import ChallengeSetup
        setup_req = ChallengeSetup(
            challenge_id="challenge_adv",
            persona_id=self.persona3.id,
            user_id=self.user1.id
        )
        setup_res = await setup_challenge_session(self.db, setup_req)
        
        # Complete session
        from app.services.challenge_session import complete_challenge_session
        from app.schemas import ChallengeCompletion
        completion_req = ChallengeCompletion(
            challenge_session_id=setup_res.challenge_session_id,
            challenge_status="won",
            reason="Completed successfully",
            user_id=self.user1.id,
            challenge_id="challenge_adv"
        )
        await complete_challenge_session(self.db, completion_req)
        
        # Verify attempt log
        from app.models import ChallengeAttempt
        from sqlalchemy import select
        stmt = select(ChallengeAttempt).filter(ChallengeAttempt.challenge_session_id == setup_res.challenge_session_id)
        attempt = (await self.db.execute(stmt)).scalars().first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.difficulty, "advance")

if __name__ == "__main__":
    unittest.main()
