from app import crud
from app.schemas import MessageResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

async def get_messages_between_users(db: AsyncSession, user1_id: int, user2_id: int, limit: int = 50, offset: int = 0) -> List[MessageResponse]:
    """Fetches messages between two users with pagination directly from the database."""

    # Fetch from database
    messages = await crud.get_messages_between_users(db, user1_id, user2_id, limit, offset)

    return [MessageResponse.model_validate(m) for m in messages]

async def get_message_by_session_id(db: AsyncSession, challenge_session_id: int) -> List[MessageResponse]:
    messages = await crud.get_messages_by_challenge_session_id(db, challenge_session_id)
    return [MessageResponse.model_validate(m) for m in messages]