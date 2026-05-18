def get_all_scenarios(db: Session):
    return crud.get_all_scenarios(db)
from sqlalchemy.orm import Session
from app import models, schemas, crud

def get_scenario_by_id(db: Session, scenario_id: str):
    return crud.get_scenario_by_id(db, scenario_id)

def create_or_update_scenario(db: Session, scenario_in: schemas.ScenarioCreate):
    return crud.upsert_scenario(db, scenario_in)

def get_scenario_context(db: Session, scenario_id: str):
    return crud.get_scenario_context_by_scenario_id(db, scenario_id)
