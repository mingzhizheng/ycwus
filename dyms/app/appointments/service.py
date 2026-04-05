import secrets
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.appointments.scheduler import calc_slot, check_slot_available
from app.appointments.state_machine import get_transition, is_valid_transition
from app.utils.audit import audit


async def create_appointment(db: AsyncSession, user: dict, data: dict) -> dict:
    """Create an appointment and attempt auto-confirmation."""
    # Determine cargo type from ASN if linked
    cargo_type = "PALLETIZED"
    if data.get("asn_id"):
        asn_result = await db.execute(
            text("SELECT cargo_type FROM asns WHERE id = :id AND status = 'ACTIVE'"),
            {"id": data["asn_id"]},
        )
        asn = asn_result.mappings().first()
        if asn:
            cargo_type = asn["cargo_type"]

    scheduled_start = data["scheduled_start"]
    if isinstance(scheduled_start, str):
        scheduled_start = datetime.fromisoformat(scheduled_start)

    start, end = calc_slot(cargo_type, scheduled_start)
    checkin_token = secrets.token_urlsafe(32)
    buffer_minutes = 30

    result = await db.execute(
        text("""
            INSERT INTO appointments (
                facility_id, asn_id, shipper_id, carrier_id,
                appointment_type, carrier_type, platform_name, platform_order_id,
                scheduled_start, scheduled_end, buffer_minutes,
                driver_name, driver_phone, truck_plate, checkin_token,
                bol_number, ltl_master_pro,
                status, created_by
            ) VALUES (
                :facility_id, :asn_id, :shipper_id, :carrier_id,
                :appointment_type, :carrier_type, :platform_name, :platform_order_id,
                :scheduled_start, :scheduled_end, :buffer_minutes,
                :driver_name, :driver_phone, :truck_plate, :checkin_token,
                :bol_number, :ltl_master_pro,
                'PENDING', :created_by
            ) RETURNING *
        """),
        {
            "facility_id": data.get("facility_id", 1),
            "asn_id": data.get("asn_id"),
            "shipper_id": user["id"],
            "carrier_id": data.get("carrier_id"),
            "appointment_type": data["appointment_type"],
            "carrier_type": data.get("carrier_type", "own"),
            "platform_name": data.get("platform_name"),
            "platform_order_id": data.get("platform_order_id"),
            "scheduled_start": start,
            "scheduled_end": end,
            "buffer_minutes": buffer_minutes,
            "driver_name": data.get("driver_name"),
            "driver_phone": data.get("driver_phone"),
            "truck_plate": data.get("truck_plate"),
            "checkin_token": checkin_token,
            "bol_number": data.get("bol_number"),
            "ltl_master_pro": data.get("ltl_master_pro"),
            "created_by": user["id"],
        },
    )
    await db.commit()
    appt = dict(result.mappings().first())

    # Link ASN if provided
    if data.get("asn_id"):
        await db.execute(
            text("INSERT INTO appointment_asns (appointment_id, asn_id) VALUES (:appt_id, :asn_id) ON CONFLICT DO NOTHING"),
            {"appt_id": appt["id"], "asn_id": data["asn_id"]},
        )
        await db.commit()

    return appt


async def get_appointment(db: AsyncSession, appointment_id: int) -> dict | None:
    result = await db.execute(
        text("""
            SELECT a.*,
                   u.display_name as shipper_name,
                   fl.code as dock_code,
                   fy.code as yard_code
            FROM appointments a
            LEFT JOIN users u ON a.shipper_id = u.id
            LEFT JOIN facility_locations fl ON a.dock_id = fl.id
            LEFT JOIN facility_locations fy ON a.yard_spot_id = fy.id
            WHERE a.id = :id
        """),
        {"id": appointment_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def list_appointments(
    db: AsyncSession,
    facility_id: int | None = None,
    shipper_id: int | None = None,
    carrier_id: int | None = None,
    status: str | None = None,
    date: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list, int]:
    where_parts = ["1=1"]
    params: dict = {}

    if facility_id:
        where_parts.append("a.facility_id = :facility_id")
        params["facility_id"] = facility_id
    if shipper_id:
        where_parts.append("a.shipper_id = :shipper_id")
        params["shipper_id"] = shipper_id
    if carrier_id:
        where_parts.append("a.carrier_id = :carrier_id")
        params["carrier_id"] = carrier_id
    if status:
        where_parts.append("a.status = :status")
        params["status"] = status
    if date:
        where_parts.append("DATE(a.scheduled_start) = :date")
        params["date"] = date

    where_clause = " AND ".join(where_parts)

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM appointments a WHERE {where_clause}"),
        params,
    )
    total = count_result.scalar()

    result = await db.execute(
        text(f"""
            SELECT a.*, u.display_name as shipper_name, fl.code as dock_code
            FROM appointments a
            LEFT JOIN users u ON a.shipper_id = u.id
            LEFT JOIN facility_locations fl ON a.dock_id = fl.id
            WHERE {where_clause}
            ORDER BY a.scheduled_start DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": limit, "offset": offset},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return rows, total


async def transition_status(
    db: AsyncSession,
    appointment_id: int,
    to_status: str,
    actor: dict,
    reason: str | None = None,
    dock_id: int | None = None,
    yard_spot_id: int | None = None,
) -> dict:
    """Execute a state machine transition with row-level locking."""
    # Lock the row
    result = await db.execute(
        text("SELECT * FROM appointments WHERE id = :id FOR UPDATE"),
        {"id": appointment_id},
    )
    appt = result.mappings().first()
    if not appt:
        from fastapi import HTTPException
        raise HTTPException(404, "Appointment not found")

    appt = dict(appt)
    from_status = appt["status"]

    if not is_valid_transition(from_status, to_status, actor["role"]):
        from fastapi import HTTPException
        raise HTTPException(400, f"Invalid transition: {from_status} -> {to_status}")

    rule = get_transition(from_status, to_status)
    now = datetime.now(timezone.utc)

    # Build update
    updates = {"status": to_status, "updated_at": now}

    # Execute actions based on transition
    actions = rule.get("actions", [])

    if "record_arrival" in actions:
        updates["actual_arrival"] = now
    if "record_unload_start" in actions:
        updates["actual_unload_start"] = now
    if "record_unload_complete" in actions:
        updates["actual_unload_complete"] = now
        if appt.get("actual_unload_start"):
            duration = int((now - appt["actual_unload_start"]).total_seconds() / 60)
            updates["actual_unload_duration"] = duration
    if "record_pickup" in actions:
        updates["actual_pickup"] = now
    if "increment_yard_move" in actions:
        updates["yard_move_count"] = (appt.get("yard_move_count") or 0) + 1
        updates["actual_yard_move_at"] = now
    if "increment_reschedule" in actions:
        updates["reschedule_count"] = (appt.get("reschedule_count") or 0) + 1

    if dock_id and "occupy_dock" in actions:
        updates["dock_id"] = dock_id
        updates["actual_dock_start"] = now
        # Mark dock as occupied
        await db.execute(
            text("UPDATE facility_locations SET status = 'OCCUPIED' WHERE id = :id"),
            {"id": dock_id},
        )

    if yard_spot_id:
        updates["yard_spot_id"] = yard_spot_id

    if "release_dock" in actions and appt.get("dock_id"):
        await db.execute(
            text("UPDATE facility_locations SET status = 'AVAILABLE' WHERE id = :id"),
            {"id": appt["dock_id"]},
        )

    if reason:
        updates["cancel_reason"] = reason
        if to_status in ("CANCELLED", "REJECTED"):
            updates["cancelled_by"] = actor["id"]
        if to_status == "AUTO_CONFIRMED":
            updates["confirmed_by"] = actor["id"]

    # Execute update
    set_parts = [f"{k} = :{k}" for k in updates]
    params = {**updates, "id": appointment_id}
    await db.execute(
        text(f"UPDATE appointments SET {', '.join(set_parts)} WHERE id = :id"),
        params,
    )

    # Audit
    await audit(
        db,
        user_id=actor["id"],
        user_display=actor.get("display_name", ""),
        action="appointment.status_change",
        target=f"appointment:{appointment_id}",
        payload={"from": from_status, "to": to_status, "reason": reason},
    )

    await db.commit()

    return await get_appointment(db, appointment_id)
