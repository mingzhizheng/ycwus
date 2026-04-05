from pydantic import BaseModel
from typing import Optional


class CheckinByToken(BaseModel):
    safety_ack: bool = False
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    device_fingerprint: Optional[str] = None


class ManualCheckin(BaseModel):
    container_number: str
    safety_ack: bool = False
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None


class ExceptionReport(BaseModel):
    appointment_id: int
    exception_type: str = "seal_broken"
    notes: Optional[str] = None
