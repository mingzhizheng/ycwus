"""
Billing Engine — Core logic for automated charge calculation.

Fee types:
  DETENTION: $50/day (day 1-3), $100/day (day 4+) after 48h free period
  NO_SHOW: $50 flat
  OVERTIME: configurable per facility
  SHUNTING: $150 per yard move (triggered by state machine)
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_billing_config(db: AsyncSession, facility_id: int) -> dict:
    """Load billing config for a facility."""
    result = await db.execute(
        text("SELECT config_key, config_value FROM billing_config WHERE facility_id = :fid"),
        {"fid": facility_id},
    )
    config = {}
    for row in result.mappings().all():
        val = row["config_value"]
        config[row["config_key"]] = json.loads(val) if isinstance(val, str) else val
    return config


def get_tier_rate(billable_days: int, tiers: list) -> float:
    """Get the daily rate for the given number of billable days."""
    for tier in tiers:
        from_day = tier.get("from_day", 1)
        to_day = tier.get("to_day")
        if to_day is None:
            to_day = 999999
        if from_day <= billable_days <= to_day:
            return tier.get("rate_per_day", 50)
    return 50  # default


async def create_billing_event(
    db: AsyncSession,
    facility_id: int,
    appointment_id: int,
    shipper_id: int,
    event_type: str,
    amount: float,
    free_period_end=None,
    billable_start=None,
    billable_end=None,
    liable_party: str = "shipper",
) -> dict:
    result = await db.execute(
        text("""
            INSERT INTO billing_events (facility_id, appointment_id, shipper_id, event_type, amount, free_period_end, billable_start, billable_end, liable_party)
            VALUES (:facility_id, :appointment_id, :shipper_id, :event_type, :amount, :free_period_end, :billable_start, :billable_end, :liable_party)
            RETURNING *
        """),
        {
            "facility_id": facility_id,
            "appointment_id": appointment_id,
            "shipper_id": shipper_id,
            "event_type": event_type,
            "amount": amount,
            "free_period_end": free_period_end,
            "billable_start": billable_start,
            "billable_end": billable_end,
            "liable_party": liable_party,
        },
    )
    await db.commit()
    return dict(result.mappings().first())


async def check_detention_for_appointment(db: AsyncSession, appt: dict, config: dict) -> dict | None:
    """Calculate detention fee for a single appointment. Returns billing event or None."""
    now = datetime.now(timezone.utc)
    complete_time = appt.get("actual_unload_complete")
    if not complete_time:
        return None

    if isinstance(complete_time, str):
        complete_time = datetime.fromisoformat(complete_time)

    free_hours = int(config.get("detention_free_hours", 48))
    tiers = config.get("detention_tiers", [{"from_day": 1, "to_day": None, "rate_per_day": 50}])
    if isinstance(tiers, str):
        tiers = json.loads(tiers)

    free_period_end = complete_time + timedelta(hours=free_hours)

    if now <= free_period_end:
        return None

    billable_days = max(1, (now - free_period_end).days + 1)
    daily_rate = get_tier_rate(billable_days, tiers)
    total = billable_days * daily_rate

    # Check if billing event already exists
    existing = await db.execute(
        text("SELECT id, amount FROM billing_events WHERE appointment_id = :aid AND event_type = 'DETENTION' AND status != 'WAIVED'"),
        {"aid": appt["id"]},
    )
    existing_row = existing.mappings().first()

    if existing_row:
        # Update existing
        if float(existing_row["amount"]) != total:
            await db.execute(
                text("UPDATE billing_events SET amount = :amount, billable_end = :now WHERE id = :id"),
                {"amount": total, "now": now, "id": existing_row["id"]},
            )
            await db.commit()
        return {"id": existing_row["id"], "amount": total, "updated": True}

    # Create new
    return await create_billing_event(
        db, appt["facility_id"], appt["id"], appt["shipper_id"],
        "DETENTION", total,
        free_period_end=free_period_end,
        billable_start=free_period_end,
        billable_end=now,
    )


async def create_noshow_charge(db: AsyncSession, appt: dict, config: dict) -> dict:
    """Create a no-show penalty charge."""
    amount = float(config.get("noshow_amount", 50))
    return await create_billing_event(
        db, appt["facility_id"], appt["id"], appt["shipper_id"],
        "NO_SHOW", amount,
    )


async def create_shunting_charge(db: AsyncSession, appt: dict) -> dict:
    """Create a shunting/yard-move charge."""
    return await create_billing_event(
        db, appt["facility_id"], appt["id"], appt["shipper_id"],
        "SHUNTING", 150.0,
    )
