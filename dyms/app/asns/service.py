from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create_asn(db: AsyncSession, shipper_id: int, data: dict) -> dict:
    result = await db.execute(
        text("""
            INSERT INTO asns (facility_id, shipper_id, container_number, cargo_type, expected_qty, qty_unit, reference_number, truck_plate, truck_company, truck_dmv, notes)
            VALUES (:facility_id, :shipper_id, :container_number, :cargo_type, :expected_qty, :qty_unit, :reference_number, :truck_plate, :truck_company, :truck_dmv, :notes)
            RETURNING *
        """),
        {"shipper_id": shipper_id, **data},
    )
    await db.commit()
    return dict(result.mappings().first())


async def get_asn(db: AsyncSession, asn_id: int) -> dict | None:
    result = await db.execute(
        text("SELECT * FROM asns WHERE id = :id"),
        {"id": asn_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def list_asns(db: AsyncSession, shipper_id: int | None = None, facility_id: int | None = None, offset: int = 0, limit: int = 20) -> tuple[list, int]:
    where_parts = ["status = 'ACTIVE'"]
    params: dict = {}

    if shipper_id:
        where_parts.append("shipper_id = :shipper_id")
        params["shipper_id"] = shipper_id
    if facility_id:
        where_parts.append("facility_id = :facility_id")
        params["facility_id"] = facility_id

    where_clause = " AND ".join(where_parts)

    count_result = await db.execute(text(f"SELECT COUNT(*) FROM asns WHERE {where_clause}"), params)
    total = count_result.scalar()

    result = await db.execute(
        text(f"SELECT * FROM asns WHERE {where_clause} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
        {**params, "limit": limit, "offset": offset},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return rows, total


async def update_asn(db: AsyncSession, asn_id: int, data: dict) -> dict | None:
    set_parts = []
    params = {"id": asn_id}
    for key, value in data.items():
        if value is not None:
            set_parts.append(f"{key} = :{key}")
            params[key] = value

    if not set_parts:
        return await get_asn(db, asn_id)

    result = await db.execute(
        text(f"UPDATE asns SET {', '.join(set_parts)} WHERE id = :id RETURNING *"),
        params,
    )
    await db.commit()
    row = result.mappings().first()
    return dict(row) if row else None


async def cancel_asn(db: AsyncSession, asn_id: int) -> dict | None:
    result = await db.execute(
        text("UPDATE asns SET status = 'CANCELLED' WHERE id = :id RETURNING *"),
        {"id": asn_id},
    )
    await db.commit()
    row = result.mappings().first()
    return dict(row) if row else None
