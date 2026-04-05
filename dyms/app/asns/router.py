from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user, require_role
from app.asns.schemas import ASNCreate, ASNUpdate
from app.asns import service

router = APIRouter()


@router.post("")
async def create_asn(
    data: ASNCreate,
    user=require_role("shipper", "admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    asn = await service.create_asn(db, user["id"], data.model_dump())
    return {"data": asn, "message": "ASN created"}


@router.get("")
async def list_asns(
    facility_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    shipper_id = user["id"] if user["role"] == "shipper" else None
    offset = (page - 1) * page_size
    rows, total = await service.list_asns(db, shipper_id=shipper_id, facility_id=facility_id, offset=offset, limit=page_size)
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/{asn_id}")
async def get_asn(
    asn_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    asn = await service.get_asn(db, asn_id)
    if not asn:
        raise HTTPException(404, "ASN not found")
    return {"data": asn}


@router.patch("/{asn_id}")
async def update_asn(
    asn_id: int,
    data: ASNUpdate,
    user=require_role("shipper", "admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    asn = await service.update_asn(db, asn_id, updates)
    if not asn:
        raise HTTPException(404, "ASN not found")
    return {"data": asn, "message": "ASN updated"}


@router.delete("/{asn_id}")
async def cancel_asn(
    asn_id: int,
    user=require_role("shipper", "admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    asn = await service.cancel_asn(db, asn_id)
    if not asn:
        raise HTTPException(404, "ASN not found")
    return {"data": asn, "message": "ASN cancelled"}
