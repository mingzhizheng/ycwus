"""
2D Capacity Engine — Dynamic scheduling based on cargo type.

Duration rules:
  PALLETIZED: 60 minutes
  FLOOR_LOAD: 180 minutes (3 hours)
  Buffer: 30 minutes added to all

Conflict detection uses SELECT FOR UPDATE row locking.
"""

from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CARGO_DURATIONS = {
    "PALLETIZED": 60,
    "FLOOR_LOAD": 180,
}
BUFFER_MINUTES = 30


def calc_duration(cargo_type: str) -> int:
    """Return total minutes including buffer."""
    return CARGO_DURATIONS.get(cargo_type, 180) + BUFFER_MINUTES


def calc_slot(cargo_type: str, scheduled_start: datetime) -> tuple[datetime, datetime]:
    """Calculate the end time for a given cargo type and start time."""
    duration = calc_duration(cargo_type)
    end = scheduled_start + timedelta(minutes=duration)
    return scheduled_start, end


async def check_slot_available(
    db: AsyncSession,
    dock_id: int,
    start: datetime,
    end: datetime,
    exclude_appointment_id: int | None = None,
) -> bool:
    """
    Check if a dock slot is available.
    Uses PostgreSQL Advisory Lock to prevent thundering herd on empty slots.
    Advisory lock key = dock_id * 1000000 + slot_hash (auto-released on tx commit).
    """
    # Compute a deterministic slot hash from dock_id + start time
    slot_hash = int(start.timestamp()) % 1000000
    lock_key = dock_id * 1000000 + slot_hash

    # Acquire advisory lock (transaction-scoped, auto-releases on commit)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    params = {"dock_id": dock_id, "start": start, "end": end}
    exclude_clause = ""
    if exclude_appointment_id:
        exclude_clause = "AND id != :exclude_id"
        params["exclude_id"] = exclude_appointment_id

    result = await db.execute(
        text(f"""
            SELECT id FROM appointments
            WHERE dock_id = :dock_id
              AND status NOT IN ('CANCELLED','REJECTED','NO_SHOW','CLOSED')
              AND scheduled_start < :end
              AND scheduled_end > :start
              {exclude_clause}
            LIMIT 1
        """),
        params,
    )
    return result.first() is None


async def find_available_slots(
    db: AsyncSession,
    facility_id: int,
    date: str,
    cargo_type: str,
    operating_start: str = "08:00",
    operating_end: str = "17:00",
) -> list[dict]:
    """Find all available slots for a given date and cargo type across all docks."""
    duration_min = calc_duration(cargo_type)

    # Get all active docks for the facility
    docks_result = await db.execute(
        text("""
            SELECT id, code FROM facility_locations
            WHERE facility_id = :fid AND location_type = 'DOCK' AND is_active = TRUE AND status != 'MAINTENANCE'
            ORDER BY sort_order
        """),
        {"fid": facility_id},
    )
    docks = docks_result.mappings().all()

    # Get existing appointments for the date
    day_start = datetime.fromisoformat(f"{date}T{operating_start}:00")
    day_end = datetime.fromisoformat(f"{date}T{operating_end}:00")

    slots = []
    for dock in docks:
        # Get all booked slots for this dock on this date
        booked_result = await db.execute(
            text("""
                SELECT scheduled_start, scheduled_end FROM appointments
                WHERE dock_id = :dock_id
                  AND status NOT IN ('CANCELLED','REJECTED','NO_SHOW','CLOSED')
                  AND scheduled_start >= :day_start
                  AND scheduled_start < :day_end
                ORDER BY scheduled_start
            """),
            {"dock_id": dock["id"], "day_start": day_start, "day_end": day_end},
        )
        booked = booked_result.mappings().all()

        # Find gaps
        current = day_start
        for b in booked:
            gap_end = b["scheduled_start"]
            if (gap_end - current).total_seconds() / 60 >= duration_min:
                slots.append({
                    "dock_id": dock["id"],
                    "dock_code": dock["code"],
                    "start": current.isoformat(),
                    "end": (current + timedelta(minutes=duration_min)).isoformat(),
                })
            current = max(current, b["scheduled_end"])

        # Check remaining time after last booking
        if (day_end - current).total_seconds() / 60 >= duration_min:
            slots.append({
                "dock_id": dock["id"],
                "dock_code": dock["code"],
                "start": current.isoformat(),
                "end": (current + timedelta(minutes=duration_min)).isoformat(),
            })

    return slots
