from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import require_role
from app.reports.queries import DOCK_UTILIZATION_QUERY, SHIPPER_RANKING_QUERY, DAILY_SUMMARY_QUERY

router = APIRouter()


@router.get("/dock-utilization")
async def dock_utilization(
    facility_id: int = Query(1),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    user=require_role("admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(DOCK_UTILIZATION_QUERY),
        {"facility_id": facility_id, "start_date": start_date, "end_date": end_date},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows}


@router.get("/shipper-ranking")
async def shipper_ranking(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    user=require_role("admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(SHIPPER_RANKING_QUERY),
        {"start_date": start_date, "end_date": end_date},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows}


@router.get("/summary")
async def daily_summary(
    facility_id: int = Query(1),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    user=require_role("admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(DAILY_SUMMARY_QUERY),
        {"facility_id": facility_id, "start_date": start_date, "end_date": end_date},
    )
    rows = [dict(r) for r in result.mappings().all()]
    return {"data": rows}
