from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_calendar_data(db: AsyncSession, facility_id: int, date: str) -> dict:
    """Get dock calendar data for a specific date."""
    # Get docks
    docks_result = await db.execute(
        text("""
            SELECT id, code, status, has_leveler, sort_order
            FROM facility_locations
            WHERE facility_id = :fid AND location_type = 'DOCK' AND is_active = TRUE
            ORDER BY sort_order
        """),
        {"fid": facility_id},
    )
    docks = [dict(r) for r in docks_result.mappings().all()]

    # Get appointments for the date
    appts_result = await db.execute(
        text("""
            SELECT a.id, a.status, a.appointment_type, a.scheduled_start, a.scheduled_end,
                   a.dock_id, a.truck_plate, a.driver_name, a.actual_arrival,
                   a.actual_unload_start, a.actual_unload_complete,
                   u.display_name as shipper_name, asn.cargo_type
            FROM appointments a
            LEFT JOIN users u ON a.shipper_id = u.id
            LEFT JOIN asns asn ON a.asn_id = asn.id
            WHERE a.facility_id = :fid
              AND DATE(a.scheduled_start) = :date
              AND a.status NOT IN ('CANCELLED', 'REJECTED')
            ORDER BY a.scheduled_start
        """),
        {"fid": facility_id, "date": date},
    )
    appointments = [dict(r) for r in appts_result.mappings().all()]

    # Get yard overview
    yard_result = await db.execute(
        text("""
            SELECT fl.id, fl.code, fl.status,
                   a.id as appointment_id, a.truck_plate, a.status as appt_status
            FROM facility_locations fl
            LEFT JOIN appointments a ON a.yard_spot_id = fl.id
                AND a.status IN ('YARD_MOVED', 'AWAITING_PICKUP')
            WHERE fl.facility_id = :fid AND fl.location_type = 'YARD' AND fl.is_active = TRUE
            ORDER BY fl.sort_order
        """),
        {"fid": facility_id},
    )
    yard = [dict(r) for r in yard_result.mappings().all()]

    return {
        "docks": docks,
        "appointments": appointments,
        "yard": yard,
        "date": date,
    }


async def drag_commit(db: AsyncSession, appointment_id: int, dock_id: int, start, end) -> dict | None:
    """Handle drag-and-drop reschedule on the calendar."""
    from app.appointments.scheduler import check_slot_available

    # Check availability with row lock
    available = await check_slot_available(db, dock_id, start, end, exclude_appointment_id=appointment_id)
    if not available:
        return None

    result = await db.execute(
        text("""
            UPDATE appointments SET
                dock_id = :dock_id,
                scheduled_start = :start,
                scheduled_end = :end,
                updated_at = NOW()
            WHERE id = :id
            RETURNING *
        """),
        {"id": appointment_id, "dock_id": dock_id, "start": start, "end": end},
    )
    await db.commit()
    row = result.mappings().first()
    return dict(row) if row else None
