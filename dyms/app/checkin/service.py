from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.geo import compute_geo_flag


async def checkin_by_token(db: AsyncSession, token: str, data: dict) -> dict:
    """Process driver check-in via QR code token."""
    result = await db.execute(
        text("""
            SELECT a.*, f.geo_lat, f.geo_lng, f.geo_radius_m
            FROM appointments a
            JOIN facilities f ON a.facility_id = f.id
            WHERE a.checkin_token = :token
              AND a.status = 'AUTO_CONFIRMED'
            FOR UPDATE
        """),
        {"token": token},
    )
    appt = result.mappings().first()
    if not appt:
        return None

    appt = dict(appt)
    now = datetime.now(timezone.utc)

    geo_flag = compute_geo_flag(
        data.get("gps_lat"),
        data.get("gps_lng"),
        float(appt["geo_lat"]) if appt.get("geo_lat") else 0,
        float(appt["geo_lng"]) if appt.get("geo_lng") else 0,
        appt.get("geo_radius_m", 500),
    )

    await db.execute(
        text("""
            UPDATE appointments SET
                status = 'CHECKED_IN',
                actual_arrival = :now,
                checkin_lat = :lat,
                checkin_lng = :lng,
                geo_flag = :geo_flag,
                safety_ack_at = :safety_ack_at,
                device_fingerprint = :fp,
                updated_at = :now
            WHERE id = :id
        """),
        {
            "id": appt["id"],
            "now": now,
            "lat": data.get("gps_lat"),
            "lng": data.get("gps_lng"),
            "geo_flag": geo_flag,
            "safety_ack_at": now if data.get("safety_ack") else None,
            "fp": data.get("device_fingerprint"),
        },
    )
    await db.commit()

    return await get_appointment_by_id(db, appt["id"])


async def get_appointment_by_token(db: AsyncSession, token: str) -> dict | None:
    result = await db.execute(
        text("""
            SELECT a.*, f.name as facility_name, f.address as facility_address,
                   fl.code as dock_code, u.display_name as shipper_name
            FROM appointments a
            JOIN facilities f ON a.facility_id = f.id
            LEFT JOIN facility_locations fl ON a.dock_id = fl.id
            LEFT JOIN users u ON a.shipper_id = u.id
            WHERE a.checkin_token = :token
        """),
        {"token": token},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_appointment_by_id(db: AsyncSession, appt_id: int) -> dict | None:
    result = await db.execute(
        text("SELECT * FROM appointments WHERE id = :id"),
        {"id": appt_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None
