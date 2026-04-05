"""Every 5 minutes: Check for overdue AUTO_CONFIRMED appointments and mark as NO_SHOW."""

import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import async_session
from app.billing.engine import get_billing_config, create_noshow_charge

logger = structlog.get_logger()


async def check_noshow():
    async with async_session() as db:
        now = datetime.now(timezone.utc)

        # Get tolerance from config
        config = await get_billing_config(db, facility_id=1)
        tolerance = int(config.get("late_tolerance_minutes", 30))

        # Find overdue appointments
        cutoff = now - timedelta(minutes=tolerance)
        result = await db.execute(
            text("""
                SELECT id, facility_id, shipper_id, scheduled_start
                FROM appointments
                WHERE status = 'AUTO_CONFIRMED'
                  AND scheduled_start < :cutoff
            """),
            {"cutoff": cutoff},
        )
        overdue = result.mappings().all()

        for appt in overdue:
            appt = dict(appt)
            logger.info("noshow_detected", appointment_id=appt["id"])

            # Mark as NO_SHOW
            await db.execute(
                text("UPDATE appointments SET status = 'NO_SHOW', updated_at = :now WHERE id = :id"),
                {"id": appt["id"], "now": now},
            )

            # Create penalty charge
            await create_noshow_charge(db, appt, config)

            await db.commit()
            logger.info("noshow_processed", appointment_id=appt["id"])
