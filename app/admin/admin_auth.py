from fastapi import Depends, HTTPException, status

from app import models
from app.routers.auth import get_current_user


async def get_current_admin_user(
    current_user: models.Persona = Depends(get_current_user),
) -> models.Persona:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user
