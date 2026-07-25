import unittest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app import cache, schemas
from app.database import Base
from app.models import Persona, AdminAuditLog
from app.admin import persona_admin_service as p_service

ADMIN_ID = 920001


class TestAdminPersonas(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.SessionLocal = async_sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.db = self.SessionLocal()
        cache.invalidate_cache(cache.create_persona_key(ADMIN_ID))

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()
        cache.invalidate_cache(cache.create_persona_key(ADMIN_ID))

    async def _create_test_persona(self) -> schemas.AdminPersonaDetail:
        persona_in = schemas.AdminPersonaCreate(
            name="Test Persona",
            desc="A test persona",
            traits={"brain": {"threat_sensitivity": 30.0}},
            image_url="",
        )
        return await p_service.create_persona(self.db, persona_in)

    async def test_create_persona_defaults_ai_and_active(self):
        created = await self._create_test_persona()
        self.assertTrue(created.is_active)
        self.assertFalse(created.is_human)
        self.assertFalse(created.is_admin)

    async def test_list_personas_excludes_human_personas(self):
        await self._create_test_persona()
        human = Persona(name="A Human", desc="", is_human=True, image_url="", traits={})
        self.db.add(human)
        await self.db.commit()

        results = await p_service.list_personas(self.db)
        names = [r.name for r in results]
        self.assertIn("Test Persona", names)
        self.assertNotIn("A Human", names)

    async def test_partial_update_only_changes_provided_fields(self):
        created = await self._create_test_persona()

        update_in = schemas.AdminPersonaUpdate(name="Renamed Persona")
        updated = await p_service.update_persona(self.db, created.id, update_in)

        self.assertEqual(updated.name, "Renamed Persona")
        self.assertEqual(updated.desc, "A test persona")  # untouched

    async def test_is_admin_grant_via_update_persists(self):
        created = await self._create_test_persona()
        self.assertFalse(created.is_admin)

        update_in = schemas.AdminPersonaUpdate(is_admin=True)
        updated = await p_service.update_persona(self.db, created.id, update_in)
        self.assertTrue(updated.is_admin)

        row = await self.db.get(Persona, created.id)
        self.assertTrue(row.is_admin)

    async def test_update_invalidates_cache(self):
        created = await self._create_test_persona()

        key = cache.create_persona_key(created.id)
        cache.store_cache(key, {"id": created.id, "name": "stale-cached-name"})
        self.assertIsNotNone(cache.retrieve_cache(key))

        await p_service.update_persona(self.db, created.id, schemas.AdminPersonaUpdate(name="Fresh Name"))

        self.assertIsNone(cache.retrieve_cache(key))

    async def test_soft_delete_deactivates_without_removing_row(self):
        created = await self._create_test_persona()

        deleted = await p_service.soft_delete_persona(self.db, created.id, admin_id=ADMIN_ID)
        self.assertFalse(deleted.is_active)

        row = await self.db.get(Persona, created.id)
        self.assertIsNotNone(row)
        self.assertFalse(row.is_active)

        logs = (await self.db.execute(
            select(AdminAuditLog).filter(AdminAuditLog.target_id == str(created.id))
        )).scalars().all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].action, "persona_soft_delete")
        self.assertEqual(logs[0].admin_id, ADMIN_ID)

    async def test_soft_delete_invalidates_cache(self):
        created = await self._create_test_persona()
        key = cache.create_persona_key(created.id)
        cache.store_cache(key, {"id": created.id, "name": "stale-cached-name"})

        await p_service.soft_delete_persona(self.db, created.id, admin_id=ADMIN_ID)

        self.assertIsNone(cache.retrieve_cache(key))

    async def test_missing_persona_operations_return_none(self):
        self.assertIsNone(await p_service.get_persona(self.db, 999999))
        self.assertIsNone(await p_service.update_persona(self.db, 999999, schemas.AdminPersonaUpdate(name="x")))
        self.assertIsNone(await p_service.soft_delete_persona(self.db, 999999, admin_id=ADMIN_ID))

    async def test_brain_trait_out_of_bounds_rejected(self):
        with self.assertRaises(ValidationError):
            schemas.AdminPersonaCreate(
                name="Bad Persona",
                desc="",
                traits={"brain": {"threat_sensitivity": 150.0}},
                image_url="",
            )

    async def test_brain_trait_negative_rejected(self):
        with self.assertRaises(ValidationError):
            schemas.AdminPersonaCreate(
                name="Bad Persona",
                desc="",
                traits={"brain": {"empathic_resonance": -1.0}},
                image_url="",
            )


if __name__ == "__main__":
    unittest.main()
