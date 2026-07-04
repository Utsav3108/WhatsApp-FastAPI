import unittest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from app.database import Base
from app.models import Persona, Challenge, ChallengeSession, ChallengeAttempt, Message, AIContentReport
from app.routers.persona import delete_user_profile

class TestProfileDeletion(unittest.IsolatedAsyncioTestCase):

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
        self.user = Persona(id=1, name="Human User", desc="Human desc", traits="", is_human=True)
        self.opponent = Persona(id=2, name="AI Opponent", desc="AI desc", traits="", is_human=False)
        self.db.add_all([self.user, self.opponent])
        await self.db.flush()

        # 3. Seed mock challenge
        self.challenge = Challenge(
            id="test_challenge",
            title="Test Challenge",
            for_user=True,
            selected_persona_id=self.user.id
        )
        self.db.add(self.challenge)
        await self.db.flush()

        # 4. Seed mock session
        self.session = ChallengeSession(
            id=10,
            user_id=self.user.id,
            challenge_id=self.challenge.id,
            persona_id=self.opponent.id,
            status="active"
        )
        self.db.add(self.session)
        await self.db.flush()

        # 5. Seed mock attempt
        self.attempt = ChallengeAttempt(
            challenge_session_id=self.session.id,
            challenge_id=self.challenge.id,
            user_id=self.user.id,
            persona_id=self.opponent.id,
            won=True
        )
        self.db.add(self.attempt)
        await self.db.flush()

        # 6. Seed mock message
        self.message = Message(
            id=100,
            sender_id=self.user.id,
            receiver_id=self.opponent.id,
            text="Hello AI"
        )
        self.db.add(self.message)
        await self.db.flush()

        # 7. Seed mock report
        self.report = AIContentReport(
            id=1000,
            message_id=self.message.id,
            conversation_id=self.session.id,
            persona_id=self.opponent.id,
            ai_response="Rep response",
            reason="harassment"
        )
        self.db.add(self.report)
        await self.db.flush()

        await self.db.commit()

    async def test_delete_profile_removes_all_user_data(self):
        # Verify initial data exists
        res = await self.db.execute(select(Persona).filter(Persona.id == self.user.id))
        self.assertIsNotNone(res.scalars().first())

        # Call deletion endpoint
        response = await delete_user_profile(db=self.db, current_user=self.user)
        self.assertEqual(response["message"], "Account and all associated data deleted successfully.")

        # Verify User Persona is deleted
        res_user = await self.db.execute(select(Persona).filter(Persona.id == self.user.id))
        self.assertNullOrNone(res_user.scalars().first())

        # Verify AI Opponent Persona is NOT deleted
        res_opponent = await self.db.execute(select(Persona).filter(Persona.id == self.opponent.id))
        self.assertIsNotNone(res_opponent.scalars().first())

        # Verify Challenge attempt is deleted
        res_attempt = await self.db.execute(select(ChallengeAttempt))
        self.assertNullOrNone(res_attempt.scalars().first())

        # Verify Challenge session is deleted
        res_session = await self.db.execute(select(ChallengeSession))
        self.assertNullOrNone(res_session.scalars().first())

        # Verify Message is deleted
        res_msg = await self.db.execute(select(Message))
        self.assertNullOrNone(res_msg.scalars().first())

        # Verify AI Content Report is deleted
        res_rep = await self.db.execute(select(AIContentReport))
        self.assertNullOrNone(res_rep.scalars().first())

        # Verify Challenge selected_persona_id is nulled out
        res_challenge = await self.db.execute(select(Challenge).filter(Challenge.id == self.challenge.id))
        challenge_db = res_challenge.scalars().first()
        self.assertIsNotNone(challenge_db)
        self.assertIsNone(challenge_db.selected_persona_id)

    async def test_static_html_routes(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        
        # Test /privacy
        res_privacy = client.get("/privacy")
        self.assertEqual(res_privacy.status_code, 200)
        self.assertIn("Privacy Policy", res_privacy.text)

        # Test /privacy-policy
        res_policy = client.get("/privacy-policy")
        self.assertEqual(res_policy.status_code, 200)
        self.assertIn("Privacy Policy", res_policy.text)

        # Test /delete-account
        res_delete = client.get("/delete-account")
        self.assertEqual(res_delete.status_code, 200)
        self.assertIn("Utsav Pandya", res_delete.text)

    def assertNullOrNone(self, val):
        self.assertTrue(val is None)

if __name__ == "__main__":
    unittest.main()
