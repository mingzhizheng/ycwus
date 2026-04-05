from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis_client import get_redis
from app.middleware.rate_limit import limiter
from app.middleware.idempotency import acquire_lock, release_lock
from app.checkin.schemas import CheckinByToken, ManualCheckin, ExceptionReport
from app.checkin import service

router = APIRouter()


@router.get("/token/{token}")
async def get_appointment_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Get appointment info by check-in token (no auth required)."""
    appt = await service.get_appointment_by_token(db, token)
    if not appt:
        raise HTTPException(404, "Appointment not found or token invalid")
    return {"data": appt}


@router.post("/token/{token}")
@limiter.limit("10/minute")
async def checkin_by_token(
    request: Request,
    token: str,
    data: CheckinByToken,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Driver check-in via QR code token (no auth required)."""
    lock_key = f"lock:checkin:{token}"
    if not await acquire_lock(redis, lock_key, ttl_seconds=3):
        raise HTTPException(429, "Check-in in progress, please wait")

    try:
        if not data.safety_ack:
            raise HTTPException(400, "Safety acknowledgement required")

        result = await service.checkin_by_token(db, token, data.model_dump())
        if not result:
            raise HTTPException(404, "Appointment not found or already checked in")
        return {"data": result, "message": "Checked in successfully"}
    finally:
        await release_lock(redis, lock_key)


@router.post("/exception")
async def report_exception(
    data: ExceptionReport,
    db: AsyncSession = Depends(get_db),
):
    """Report gate exception (seal broken, damage, etc.). No auth required."""
    from app.appointments.service import transition_status

    # Create a system actor for unauthenticated exception reports
    system_actor = {"id": None, "role": "system", "display_name": "Driver (Gate)"}

    # We need to check the appointment exists and is in CHECKED_IN state
    result = await service.get_appointment_by_id(db, data.appointment_id)
    if not result:
        raise HTTPException(404, "Appointment not found")

    if result["status"] != "CHECKED_IN":
        raise HTTPException(400, "Appointment must be in CHECKED_IN status to report exception")

    # For now, just update the exception fields directly
    from sqlalchemy import text
    await db.execute(
        text("""
            UPDATE appointments SET
                status = 'EXCEPTION_AT_GATE',
                updated_at = NOW()
            WHERE id = :id
        """),
        {"id": data.appointment_id},
    )
    await db.commit()

    return {"message": "Exception reported", "appointment_id": data.appointment_id}
