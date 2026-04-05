"""Daily at facility close time: Lock overnight unfinished appointments."""

import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import async_session

logger = structlog.get_logger()


async def check_overnight():
    async with async_session() as db:
        result = await db.execute(
            text("""
                SELECT a.id, a.dock_id, a.facility_id, fl.code as dock_code
                FROM appointments a
                LEFT JOIN facility_locations fl ON a.dock_id = fl.id
                WHERE a.status IN ('DOCK_ASSIGNED', 'UNLOADING')
            """)
        )
        active = result.mappings().all()

        for appt in active:
            appt = dict(appt)
            logger.warning(
                "overnight_appointment",
                appointment_id=appt["id"],
                dock_code=appt.get("dock_code"),
            )
            # The dock remains occupied — log for dispatcher attention
            # In production, this would send notifications and lock the next-day first slot
