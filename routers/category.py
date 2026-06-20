from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, models, crud
from app.database import get_db

router = APIRouter()

@router.get("/categories", response_model=list[schemas.CategoryResponse])
async def get_all_categories(db: AsyncSession = Depends(get_db)):
    categories = await crud.get_all_categories(db)
    return categories

@router.post("/categories", response_model=schemas.CategoryResponse)
async def create_category(category_in: schemas.CategoryCreate, db: AsyncSession = Depends(get_db)):
    # Check if category already exists
    db_cat = await crud.get_category_by_name(db, category_in.name)
    if db_cat:
        raise HTTPException(status_code=400, detail="Category already exists")
    category = await crud.create_category(db, category_in)
    return category

@router.delete("/categories/{category_id}")
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    success = await crud.delete_category(db, category_id)
    if not success:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "success", "message": f"Category {category_id} deleted successfully"}

@router.put("/categories/{category_id}", response_model=schemas.CategoryResponse)
async def update_category(category_id: int, category_in: schemas.CategoryCreate, db: AsyncSession = Depends(get_db)):
    db_cat = await crud.get_category_by_id(db, category_id)
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    # Check if name is taken by another category
    other_cat = await crud.get_category_by_name(db, category_in.name)
    if other_cat and other_cat.id != category_id:
        raise HTTPException(status_code=400, detail="Category name already exists")
    updated = await crud.update_category(db, db_cat, category_in)
    return updated
