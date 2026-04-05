from pydantic import BaseModel
from typing import Optional


class DockAssign(BaseModel):
    appointment_id: int
    dock_id: int


class UnloadComplete(BaseModel):
    appointment_id: int


class YardMove(BaseModel):
    appointment_id: int
    yard_spot_id: Optional[int] = None


class TypeMismatch(BaseModel):
    appointment_id: int
    actual_cargo_type: str


class FacilityLocationCreate(BaseModel):
    facility_id: int = 1
    location_type: str  # DOCK or YARD
    code: str
    has_leveler: bool = True
    max_weight_lbs: Optional[int] = None
