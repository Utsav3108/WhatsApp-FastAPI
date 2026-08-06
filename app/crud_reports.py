from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas


async def get_message_by_id(db: AsyncSession, message_id: int):
    result = await db.execute(select(models.Message).filter(models.Message.id == message_id))
    return result.scalars().first()


async def create_ai_content_report(db: AsyncSession, report_in: schemas.AIContentReportCreate):
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


async def get_all_ai_content_reports(db: AsyncSession):
    result = await db.execute(select(models.AIContentReport).order_by(models.AIContentReport.timestamp.desc()))
    return result.scalars().all()
