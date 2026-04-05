"""Every hour: Calculate detention fees for appointments past their free period."""

import structlog
from sqlalchemy import text

from app.database import async_session
from app.billing.engine import get_billing_config, check_detention_for_appointment

logger = structlog.get_logger()


async def check_detention():
    async with async_session() as db:
        config = await get_billing_config(db, facility_id=1)

        result = await db.execute(
            text("""
                SELECT id, facility_id, shipper_id, actual_unload_complete
                FROM appointments
                WHERE status IN ('UNLOAD_COMPLETE', 'YARD_MOVED', 'AWAITING_PICKUP')
                  AND actual_unload_complete IS NOT NULL
            """)
        )
        appointments = result.mappings().all()

        for appt in appointments:
            appt = dict(appt)
            charge = await check_detention_for_appointment(db, appt, config)
            if charge:
                logger.info(
                    "detention_charge_processed",
                    appointment_id=appt["id"],
                    amount=charge.get("amount"),
                )
