from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_role
from app.calendar.schemas import DragCommit
from app.calendar import service
from app.appointments.scheduler import find_available_slots
from app.redis_client import get_redis
from app.middleware.idempotency import acquire_lock, release_lock

router = APIRouter()


@router.get("")
async def get_calendar(
    facility_id: int = Query(1),
    date: str = Query(..., description="YYYY-MM-DD"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await service.get_calendar_data(db, facility_id, date)
    return {"data": data}


@router.get("/slots")
async def get_slots(
    facility_id: int = Query(1),
    date: str = Query(..., description="YYYY-MM-DD"),
    cargo_type: str = Query("PALLETIZED"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slots = await find_available_slots(db, facility_id, date, cargo_type)
    return {"data": slots}


@router.put("/drag")
async def drag_appointment(
    data: DragCommit,
    user=require_role("dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    lock_key = f"lock:drag:{data.appointment_id}"
    if not await acquire_lock(redis, lock_key, ttl_seconds=5):
        raise HTTPException(409, "Another user is moving this appointment")

    try:
        result = await service.drag_commit(db, data.appointment_id, data.dock_id, data.start, data.end)
        if not result:
            raise HTTPException(409, "Time slot conflict — slot already occupied")
        return {"data": result, "message": "Appointment rescheduled"}
    finally:
        await release_lock(redis, lock_key)
