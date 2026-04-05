from pydantic import BaseModel
from typing import Optional
from enum import Enum


class PhotoType(str, Enum):
    TRUCK_REAR = "TRUCK_REAR"
    SEAL_PHOTO = "SEAL_PHOTO"
    DOOR_OPEN = "DOOR_OPEN"
    CLEAR_OUT = "CLEAR_OUT"
    EXCEPTION = "EXCEPTION"
    YARD_WALK = "YARD_WALK"


class EvidenceResponse(BaseModel):
    id: int
    appointment_id: int
    photo_type: str
    file_path: str
    thumbnail_path: Optional[str]
    taken_at: str
    notes: Optional[str]
