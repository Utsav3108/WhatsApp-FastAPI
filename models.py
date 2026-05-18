from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base


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



# ScenarioContext table
from sqlalchemy.orm import relationship

class ScenarioContext(Base):
    __tablename__ = "scenario_contexts"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(String, ForeignKey("scenarios.id"), unique=True)
    setting = Column(String)
    goal = Column(String)
    stakes = Column(String)
    platform = Column(String)
    scenario = relationship("Scenario", back_populates="context")


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(String, primary_key=True, index=True)
    title = Column(String)
    image_url = Column(String)
    context = relationship("ScenarioContext", uselist=False, back_populates="scenario", cascade="all, delete-orphan")

