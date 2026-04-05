from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_role
from app.dock.schemas import DockAssign, UnloadComplete, YardMove, TypeMismatch, FacilityLocationCreate
from app.dock import service
from app.appointments.service import transition_status

router = APIRouter()


@router.get("/locations")
async def list_locations(
    facility_id: int = Query(1),
    location_type: str = Query(None),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locations = await service.get_facility_locations(db, facility_id, location_type)
    return {"data": locations}


@router.post("/locations")
async def create_location(
    data: FacilityLocationCreate,
    user=require_role("admin"),
    db: AsyncSession = Depends(get_db),
):
    location = await service.create_facility_location(db, data.model_dump())
    return {"data": location, "message": "Location created"}


@router.post("/assign")
async def assign_dock(
    data: DockAssign,
    user=require_role("dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
):
    appt = await transition_status(
        db, data.appointment_id, "DOCK_ASSIGNED", user, dock_id=data.dock_id,
    )
    return {"data": appt, "message": "Dock assigned"}


@router.post("/unload-complete")
async def unload_complete(
    data: UnloadComplete,
    user=require_role("warehouse_staff", "dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
):
    appt = await transition_status(db, data.appointment_id, "UNLOAD_COMPLETE", user)
    return {"data": appt, "message": "Unload complete"}


@router.post("/yard-move")
async def yard_move(
    data: YardMove,
    user=require_role("warehouse_staff", "dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
):
    appt = await transition_status(
        db, data.appointment_id, "YARD_MOVED", user, yard_spot_id=data.yard_spot_id,
    )
    return {"data": appt, "message": "Yard move completed, dock released"}


@router.post("/type-mismatch")
async def report_type_mismatch(
    data: TypeMismatch,
    user=require_role("warehouse_staff", "dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    await db.execute(
        text("""
            UPDATE appointments SET
                cargo_type_actual = :actual,
                cargo_type_mismatch = TRUE,
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": data.appointment_id, "actual": data.actual_cargo_type},
    )
    await db.commit()
    return {"message": "Type mismatch recorded", "appointment_id": data.appointment_id}


@router.get("/yard/inventory")
async def yard_inventory(
    facility_id: int = Query(1),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await service.get_yard_inventory(db, facility_id)
    return {"data": items}


@router.patch("/locations/{location_id}/status")
async def update_location_status(
    location_id: int,
    status: str = Query(...),
    user=require_role("dispatcher", "admin"),
    db: AsyncSession = Depends(get_db),
):
    location = await service.update_location_status(db, location_id, status)
    if not location:
        raise HTTPException(404, "Location not found")
    return {"data": location, "message": f"Status updated to {status}"}
