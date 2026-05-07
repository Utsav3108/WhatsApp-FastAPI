from pydantic import BaseModel
from typing import Any, List, Optional

class PresidentCreate(BaseModel):
    name: str
    desc: str
    traits: str
    image_url: str

class PresidentResponse(BaseModel):
    id: int
    name: str
    desc: str
    image_url: str

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    sender_id: int
    receiver_id: int
    text: str
    image_object_name: Optional[str] = None

class MessageResponse(MessageCreate):
    id: int

    class Config:
        from_attributes = True


class BaseResponse(BaseModel):
    success: bool
    data: Any
    message: Optional[str] = None