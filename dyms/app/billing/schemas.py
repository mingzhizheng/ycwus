from pydantic import BaseModel
from typing import Optional


class WaiveRequest(BaseModel):
    reason: str


class BillingEventResponse(BaseModel):
    id: int
    facility_id: int
    appointment_id: int
    shipper_id: int
    event_type: str
    amount: float
    currency: str
    status: str
    liable_party: str
    created_at: str
