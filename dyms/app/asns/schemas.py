from pydantic import BaseModel
from typing import Optional
from enum import Enum


class CargoType(str, Enum):
    PALLETIZED = "PALLETIZED"
    FLOOR_LOAD = "FLOOR_LOAD"


class QtyUnit(str, Enum):
    BOXES = "BOXES"
    PALLETS = "PALLETS"


class ASNCreate(BaseModel):
    facility_id: int = 1
    container_number: Optional[str] = None
    cargo_type: CargoType
    expected_qty: Optional[int] = None
    qty_unit: QtyUnit = QtyUnit.BOXES
    reference_number: Optional[str] = None
    truck_plate: Optional[str] = None
    truck_company: Optional[str] = None
    truck_dmv: Optional[str] = None
    notes: Optional[str] = None


class ASNUpdate(BaseModel):
    container_number: Optional[str] = None
    cargo_type: Optional[CargoType] = None
    expected_qty: Optional[int] = None
    qty_unit: Optional[QtyUnit] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class ASNResponse(BaseModel):
    id: int
    facility_id: int
    shipper_id: int
    container_number: Optional[str]
    cargo_type: str
    expected_qty: Optional[int]
    qty_unit: str
    reference_number: Optional[str]
    notes: Optional[str]
    status: str
    created_at: str
