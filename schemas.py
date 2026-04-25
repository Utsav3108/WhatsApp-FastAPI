from pydantic import BaseModel

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

class MessageResponse(MessageCreate):
    id: int

    class Config:
        from_attributes = True