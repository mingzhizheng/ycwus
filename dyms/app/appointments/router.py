from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_role
from app.appointments.schemas import AppointmentCreate, AppointmentUpdate, StatusTransition
from app.appointments import service
from app.appointments.scheduler import find_available_slots

router = APIRouter()


@router.post("")
async def create_appointment(
    data: AppointmentCreate,
    user=require_role("shipper", "carrier", "admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    appt = await service.create_appointment(db, user, data.model_dump())
    return {"data": appt, "message": "Appointment created"}


@router.get("")
async def list_appointments(
    facility_id: int = Query(None),
    status: str = Query(None),
    date: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    shipper_id = user["id"] if user["role"] == "shipper" else None
    carrier_id = user["id"] if user["role"] == "carrier" else None
    offset = (page - 1) * page_size
    rows, total = await service.list_appointments(
        db, facility_id=facility_id, shipper_id=shipper_id, carrier_id=carrier_id,
        status=status, date=date, offset=offset, limit=page_size,
    )
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/slots")
async def get_available_slots(
    facility_id: int = Query(1),
    date: str = Query(..., description="YYYY-MM-DD"),
    cargo_type: str = Query("PALLETIZED"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slots = await find_available_slots(db, facility_id, date, cargo_type)
    return {"data": slots}


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    appt = await service.get_appointment(db, appointment_id)
    if not appt:
        raise HTTPException(404, "Appointment not found")
    return {"data": appt}


@router.patch("/{appointment_id}/status")
async def transition_status(
    appointment_id: int,
    data: StatusTransition,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    appt = await service.transition_status(
        db, appointment_id, data.to_status.value, user,
        reason=data.reason, dock_id=data.dock_id, yard_spot_id=data.yard_spot_id,
    )
    return {"data": appt, "message": f"Status changed to {data.to_status.value}"}


@router.patch("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    reason: str = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    appt = await service.transition_status(
        db, appointment_id, "CANCELLED", user, reason=reason,
    )
    return {"data": appt, "message": "Appointment cancelled"}
