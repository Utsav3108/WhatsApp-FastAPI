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
    scenario_id: Optional[str] = None

class MessageResponse(MessageCreate):
    id: int

    class Config:
        from_attributes = True


# Scenario schemas
from typing import Dict, Optional

class ScenarioContextBase(BaseModel):
    setting: str
    goal: str
    stakes: str
    platform: str

class ScenarioContextCreate(ScenarioContextBase):
    pass

class ScenarioContextResponse(ScenarioContextBase):
    id: int
    scenario_id: str

    class Config:
        from_attributes = True

class ScenarioBase(BaseModel):
    title: str
    image_url: str

class ScenarioCreate(ScenarioBase):
    id: str
    context: ScenarioContextCreate

class ScenarioResponse(ScenarioBase):
    id: str
    context: Optional[ScenarioContextResponse]

    class Config:
        from_attributes = True
