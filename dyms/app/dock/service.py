from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_facility_locations(db: AsyncSession, facility_id: int, location_type: str | None = None) -> list:
    where = "facility_id = :fid AND is_active = TRUE"
    params = {"fid": facility_id}
    if location_type:
        where += " AND location_type = :lt"
        params["lt"] = location_type

    result = await db.execute(
        text(f"SELECT * FROM facility_locations WHERE {where} ORDER BY sort_order"),
        params,
    )
    return [dict(r) for r in result.mappings().all()]


async def create_facility_location(db: AsyncSession, data: dict) -> dict:
    result = await db.execute(
        text("""
            INSERT INTO facility_locations (facility_id, location_type, code, has_leveler, max_weight_lbs)
            VALUES (:facility_id, :location_type, :code, :has_leveler, :max_weight_lbs)
            RETURNING *
        """),
        data,
    )
    await db.commit()
    return dict(result.mappings().first())


async def update_location_status(db: AsyncSession, location_id: int, status: str) -> dict | None:
    result = await db.execute(
        text("UPDATE facility_locations SET status = :status WHERE id = :id RETURNING *"),
        {"id": location_id, "status": status},
    )
    await db.commit()
    row = result.mappings().first()
    return dict(row) if row else None


async def get_yard_inventory(db: AsyncSession, facility_id: int) -> list:
    """Get all containers currently in the yard."""
    result = await db.execute(
        text("""
            SELECT a.id, a.status, a.truck_plate, a.actual_unload_complete, a.actual_yard_move_at,
                   a.yard_move_count, a.scheduled_start, a.appointment_type,
                   fl.code as yard_code, u.display_name as shipper_name
            FROM appointments a
            LEFT JOIN facility_locations fl ON a.yard_spot_id = fl.id
            LEFT JOIN users u ON a.shipper_id = u.id
            WHERE a.facility_id = :fid
              AND a.status IN ('UNLOAD_COMPLETE', 'YARD_MOVED', 'AWAITING_PICKUP')
            ORDER BY a.actual_unload_complete
        """),
        {"fid": facility_id},
    )
    return [dict(r) for r in result.mappings().all()]
