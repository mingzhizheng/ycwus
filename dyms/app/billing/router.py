from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_role
from app.billing.schemas import WaiveRequest
from app.utils.audit import audit
from app.redis_client import get_redis
from app.middleware.idempotency import acquire_lock, release_lock

router = APIRouter()


@router.get("/events")
async def list_billing_events(
    facility_id: int = Query(1),
    shipper_id: int = Query(None),
    event_type: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    where_parts = ["b.facility_id = :fid"]
    params: dict = {"fid": facility_id}

    if user["role"] == "shipper":
        where_parts.append("b.shipper_id = :sid")
        params["sid"] = user["id"]
    elif shipper_id:
        where_parts.append("b.shipper_id = :sid")
        params["sid"] = shipper_id

    if event_type:
        where_parts.append("b.event_type = :et")
        params["et"] = event_type
    if status:
        where_parts.append("b.status = :st")
        params["st"] = status

    where_clause = " AND ".join(where_parts)
    offset = (page - 1) * page_size

    count_result = await db.execute(text(f"SELECT COUNT(*) FROM billing_events b WHERE {where_clause}"), params)
    total = count_result.scalar()

    result = await db.execute(
        text(f"""
            SELECT b.*, u.display_name as shipper_name
            FROM billing_events b
            LEFT JOIN users u ON b.shipper_id = u.id
            WHERE {where_clause}
            ORDER BY b.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.patch("/events/{event_id}/waive")
async def waive_billing_event(
    event_id: int,
    data: WaiveRequest,
    user=require_role("admin"),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    lock_key = f"lock:waive:{event_id}"
    if not await acquire_lock(redis, lock_key, ttl_seconds=3):
        raise HTTPException(429, "Waive operation in progress")

    try:
        result = await db.execute(
            text("UPDATE billing_events SET status = 'WAIVED', waived_by = :uid, waive_reason = :reason WHERE id = :id AND status = 'PENDING' RETURNING *"),
            {"id": event_id, "uid": user["id"], "reason": data.reason},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(404, "Billing event not found or already processed")

        await audit(
            db, user["id"], user.get("display_name"), "billing.waive",
            f"billing_event:{event_id}", {"reason": data.reason},
        )
        await db.commit()
        return {"data": dict(row), "message": "Billing event waived"}
    finally:
        await release_lock(redis, lock_key)


@router.get("/summary")
async def billing_summary(
    facility_id: int = Query(1),
    period_start: str = Query(None),
    period_end: str = Query(None),
    user=require_role("admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"fid": facility_id}
    date_filter = ""
    if period_start:
        date_filter += " AND b.created_at >= :ps"
        params["ps"] = period_start
    if period_end:
        date_filter += " AND b.created_at <= :pe"
        params["pe"] = period_end

    result = await db.execute(
        text(f"""
            SELECT
                event_type,
                status,
                COUNT(*) as count,
                SUM(amount) as total_amount
            FROM billing_events b
            WHERE facility_id = :fid {date_filter}
            GROUP BY event_type, status
            ORDER BY event_type, status
        """),
        params,
    )
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows}
