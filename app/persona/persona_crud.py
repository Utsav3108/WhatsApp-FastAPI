from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def get_challenge_attempts_by_user(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(models.ChallengeAttempt).filter(models.ChallengeAttempt.user_id == user_id)
    )
    return result.scalars().all()


async def get_practice_partner_persona_ids(db: AsyncSession, user_id: int) -> list[int]:
    """Persona ids the user has exchanged non-challenge messages with, either direction."""
    sent_res = await db.execute(
        select(models.Message.receiver_id)
        .filter(models.Message.sender_id == user_id, models.Message.challenge_session_id == None)
        .distinct()
    )
    received_res = await db.execute(
        select(models.Message.sender_id)
        .filter(models.Message.receiver_id == user_id, models.Message.challenge_session_id == None)
        .distinct()
    )
    sent_to_personas = [row[0] for row in sent_res.all()]
    received_from_personas = [row[0] for row in received_res.all()]
    return list(set(sent_to_personas + received_from_personas))


async def get_recent_attempts_log(db: AsyncSession, user_id: int, limit: int = 5):
    """Returns rows of (ChallengeAttempt, challenge_title, persona_name)."""
    stmt = (
        select(models.ChallengeAttempt, models.Challenge.title, models.Persona.name)
        .join(models.Challenge, models.ChallengeAttempt.challenge_id == models.Challenge.id)
        .join(models.Persona, models.ChallengeAttempt.persona_id == models.Persona.id)
        .filter(models.ChallengeAttempt.user_id == user_id)
        .order_by(models.ChallengeAttempt.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.all()


async def delete_user_account_cascade(db: AsyncSession, user_id: int) -> None:
    """Deletes a user Persona and every row referencing it across domains."""
    # 1. Null out selected_persona_id in challenges
    await db.execute(
        update(models.Challenge)
        .where(models.Challenge.selected_persona_id == user_id)
        .values(selected_persona_id=None)
    )

    # 2. Get message IDs and session IDs
    res_sessions = await db.execute(
        select(models.ChallengeSession.id).filter(models.ChallengeSession.user_id == user_id)
    )
    session_ids = [row[0] for row in res_sessions.all()]

    res_messages = await db.execute(
        select(models.Message.id).filter(
            (models.Message.sender_id == user_id) | (models.Message.receiver_id == user_id)
        )
    )
    message_ids = [row[0] for row in res_messages.all()]

    # 3. Delete AI Content Reports
    if message_ids:
        await db.execute(
            delete(models.AIContentReport).filter(models.AIContentReport.message_id.in_(message_ids))
        )
    if session_ids:
        await db.execute(
            delete(models.AIContentReport).filter(models.AIContentReport.conversation_id.in_(session_ids))
        )
    # Also delete reports created by/against the user persona directly
    await db.execute(
        delete(models.AIContentReport).filter(models.AIContentReport.persona_id == user_id)
    )

    # 4. Delete Challenge Attempts
    await db.execute(
        delete(models.ChallengeAttempt).filter(
            (models.ChallengeAttempt.user_id == user_id) | (models.ChallengeAttempt.persona_id == user_id)
        )
    )

    # 5. Delete Messages
    await db.execute(
        delete(models.Message).filter(
            (models.Message.sender_id == user_id) | (models.Message.receiver_id == user_id)
        )
    )

    # 6. Delete Challenge Sessions
    await db.execute(
        delete(models.ChallengeSession).filter(
            (models.ChallengeSession.user_id == user_id) | (models.ChallengeSession.persona_id == user_id)
        )
    )

    # 7. Finally delete the User Persona itself
    await db.execute(
        delete(models.Persona).filter(models.Persona.id == user_id)
    )

    await db.commit()
