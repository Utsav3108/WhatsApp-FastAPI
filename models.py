from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from database import Base


from sqlalchemy import DateTime
from datetime import datetime, timezone

class President(Base):
    __tablename__ = "presidents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    desc = Column(String)
    traits = Column(String)
    image_url = Column(String, default="")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("presidents.id"))
    receiver_id = Column(Integer, ForeignKey("presidents.id"))
    text = Column(String)
    is_user = Column(Boolean)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    image_object_name = Column(String, nullable=True)

