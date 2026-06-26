import math
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.database import get_db
from app.routers.auth import get_current_user
from app import models

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=schemas.PaginatedMessagesResponse)
async def get_conversations(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=10, ge=1, le=100, description="Number of messages per page"),
    sender_id: int | None = Query(default=None, description="Sender persona ID (persona chat)"),
    receiver_id: int | None = Query(default=None, description="Receiver persona ID (persona chat)"),
    challenge_session_id: int | None = Query(default=None, description="Challenge session ID"),
    attempt_session_id: int | None = Query(default=None, description="Past attempt session ID (read-only history)"),
    db: AsyncSession = Depends(get_db),
    current_user: models.Persona = Depends(get_current_user),
):
    messages: list = []
    total_count: int = 0

    if attempt_session_id is not None:
        messages, total_count = await crud.get_messages_paginated_by_session(
            db, challenge_session_id=attempt_session_id, page=page, page_size=page_size
        )
    elif challenge_session_id is not None:
        messages, total_count = await crud.get_messages_paginated_by_session(
            db, challenge_session_id=challenge_session_id, page=page, page_size=page_size
        )
    elif sender_id is not None and receiver_id is not None:
        if current_user.id not in (sender_id, receiver_id):
            raise HTTPException(status_code=403, detail="Forbidden: You are not a participant in this conversation.")
        messages, total_count = await crud.get_messages_paginated_between_users(
            db, user1_id=sender_id, user2_id=receiver_id, page=page, page_size=page_size
        )
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide one of: (sender_id + receiver_id) for persona chat, "
                "challenge_session_id for an ongoing session, "
                "or attempt_session_id for a past attempt."
            ),
        )

    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    has_more = page < total_pages

    return schemas.PaginatedMessagesResponse(
        messages=[schemas.MessageResponse.model_validate(m) for m in messages],
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
        has_more=has_more,
    )
