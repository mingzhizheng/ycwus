from pydantic import BaseModel
from typing import Optional
from enum import Enum
from datetime import datetime


class AppointmentType(str, Enum):
    LIVE = "LIVE"
    DROP = "DROP"


class CarrierType(str, Enum):
    OWN = "own"
    PLATFORM = "platform"
    SELF = "self"


class AppointmentStatus(str, Enum):
    PENDING = "PENDING"
    AUTO_CONFIRMED = "AUTO_CONFIRMED"
    REJECTED = "REJECTED"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
    CHECKED_IN = "CHECKED_IN"
    EXCEPTION_AT_GATE = "EXCEPTION_AT_GATE"
    DOCK_ASSIGNED = "DOCK_ASSIGNED"
    UNLOADING = "UNLOADING"
    UNLOAD_COMPLETE = "UNLOAD_COMPLETE"
    YARD_MOVED = "YARD_MOVED"
    AWAITING_PICKUP = "AWAITING_PICKUP"
    PICKED_UP = "PICKED_UP"
    CLOSED = "CLOSED"
    NO_SHOW = "NO_SHOW"


class AppointmentCreate(BaseModel):
    facility_id: int = 1
    asn_id: Optional[int] = None
    appointment_type: AppointmentType
    carrier_type: CarrierType = CarrierType.OWN
    platform_name: Optional[str] = None
    platform_order_id: Optional[str] = None
    scheduled_start: datetime
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    truck_plate: Optional[str] = None
    bol_number: Optional[str] = None
    ltl_master_pro: Optional[str] = None


class AppointmentUpdate(BaseModel):
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    truck_plate: Optional[str] = None
    bol_number: Optional[str] = None


class StatusTransition(BaseModel):
    to_status: AppointmentStatus
    reason: Optional[str] = None
    dock_id: Optional[int] = None
    yard_spot_id: Optional[int] = None
