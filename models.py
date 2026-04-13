from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from database import Base


from sqlalchemy import DateTime
from datetime import datetime, timezone


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    desc = Column(String)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    text = Column(String)
    is_user = Column(Boolean)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

