from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import crud, models, schemas
from app.database import get_db

router = APIRouter(tags=["reports"])

@router.post("/reports/ai-content", response_model=schemas.AIContentReportResponse)
async def create_ai_content_report(
    report_in: schemas.AIContentReportCreate,
    db: AsyncSession = Depends(get_db)
):
    # Verify message exists
    msg_res = await db.execute(select(models.Message).filter(models.Message.id == report_in.message_id))
    msg = msg_res.scalars().first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Create report
    db_report = models.AIContentReport(
        message_id=report_in.message_id,
        conversation_id=report_in.conversation_id,
        persona_id=report_in.persona_id,
        user_prompt=report_in.user_prompt,
        ai_response=report_in.ai_response,
        reason=report_in.reason,
        description=report_in.description
    )
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)
    return db_report

@router.get("/reports/ai-content", response_model=list[schemas.AIContentReportResponse])
async def get_ai_content_reports(
    db: AsyncSession = Depends(get_db)
):
    # Retrieve all reports ordered by timestamp DESC
    result = await db.execute(select(models.AIContentReport).order_by(models.AIContentReport.timestamp.desc()))
    reports = result.scalars().all()
    return reports
