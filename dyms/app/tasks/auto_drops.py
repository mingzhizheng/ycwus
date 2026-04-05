"""Daily at 06:00: Auto-schedule DROP appointments that have been pending > 24h."""

import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import async_session
from app.appointments.scheduler import find_available_slots

logger = structlog.get_logger()


async def auto_schedule_drops():
    async with async_session() as db:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=24)

        # Find DROP appointments that are still PENDING after 24 hours
        result = await db.execute(
            text("""
                SELECT a.id, a.facility_id, a.asn_id, a.shipper_id
                FROM appointments a
                WHERE a.appointment_type = 'DROP'
                  AND a.status = 'PENDING'
                  AND a.created_at < :cutoff
            """),
            {"cutoff": cutoff},
        )
        pending_drops = result.mappings().all()

        today = now.strftime("%Y-%m-%d")

        for drop in pending_drops:
            drop = dict(drop)
            logger.info("auto_scheduling_drop", appointment_id=drop["id"])

            # Find the earliest available slot
            slots = await find_available_slots(db, drop["facility_id"], today, "PALLETIZED")
            if slots:
                earliest = slots[0]
                await db.execute(
                    text("""
                        UPDATE appointments SET
                            status = 'AUTO_CONFIRMED',
                            dock_id = :dock_id,
                            scheduled_start = :start,
                            scheduled_end = :end,
                            updated_at = :now
                        WHERE id = :id
                    """),
                    {
                        "id": drop["id"],
                        "dock_id": earliest["dock_id"],
                        "start": earliest["start"],
                        "end": earliest["end"],
                        "now": now,
                    },
                )
                await db.commit()
                logger.info("drop_auto_scheduled", appointment_id=drop["id"], dock=earliest["dock_code"])
            else:
                logger.warning("no_slots_for_drop", appointment_id=drop["id"])
