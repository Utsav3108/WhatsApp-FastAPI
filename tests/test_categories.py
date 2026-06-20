import unittest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base
from app.models import Category
from app import schemas, crud

class TestCategoriesAPI(unittest.IsolatedAsyncioTestCase):

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
        # Seed mock category
        self.cat1 = Category(
            id=1,
            name="Business & Career",
            keywords=["Finance", "Business"],
            icon="business_center",
            gradient_colors=["#000000"]
        )
        self.db.add(self.cat1)
        await self.db.commit()

    async def test_get_all_categories(self):
        categories = await crud.get_all_categories(self.db)
        self.assertEqual(len(categories), 1)
        self.assertEqual(categories[0].name, "Business & Career")

    async def test_create_category(self):
        # Create unique category
        new_cat = schemas.CategoryCreate(
            name="Dating",
            keywords=["Romance"],
            icon="favorite",
            gradient_colors=["#B71C1C"]
        )
        db_cat = await crud.create_category(self.db, new_cat)
        self.assertIsNotNone(db_cat.id)
        self.assertEqual(db_cat.name, "Dating")

        # Test duplicate check on router level
        from app.routers.category import create_category
        from fastapi import HTTPException

        duplicate_cat = schemas.CategoryCreate(
            name="Business & Career"
        )
        with self.assertRaises(HTTPException) as context:
            await create_category(duplicate_cat, self.db)
        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail, "Category already exists")

    async def test_delete_category(self):
        # Test deletion
        success = await crud.delete_category(self.db, 1)
        self.assertTrue(success)

        # Verify not found
        categories = await crud.get_all_categories(self.db)
        self.assertEqual(len(categories), 0)

        # Delete non-existent
        success_fail = await crud.delete_category(self.db, 999)
        self.assertFalse(success_fail)

if __name__ == "__main__":
    unittest.main()
