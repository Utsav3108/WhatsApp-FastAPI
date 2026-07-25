from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, crud_reports
from app.database import get_db

router = APIRouter(tags=["Reports"])

@router.post("/reports/ai-content", response_model=schemas.AIContentReportResponse)
async def create_ai_content_report(
    report_in: schemas.AIContentReportCreate,
    db: AsyncSession = Depends(get_db)
):
    # Verify message exists
    msg = await crud_reports.get_message_by_id(db, report_in.message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    return await crud_reports.create_ai_content_report(db, report_in)

@router.get("/reports/ai-content", response_model=list[schemas.AIContentReportResponse])
async def get_ai_content_reports(
    db: AsyncSession = Depends(get_db)
):
    return await crud_reports.get_all_ai_content_reports(db)
