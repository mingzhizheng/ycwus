from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rate_limit import limiter
from app.evidence import service

router = APIRouter()


@router.post("/upload")
@limiter.limit("60/minute")
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    appointment_id: int = Form(...),
    photo_type: str = Form(...),
    gps_lat: float = Form(None),
    gps_lng: float = Form(None),
    notes: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a single evidence photo. No auth required (driver use case)."""
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "File size exceeds 20MB limit")

    file_path, thumbnail_path = await service.validate_and_save(
        content, file.filename, appointment_id, photo_type,
    )

    evidence = await service.create_evidence(
        db, appointment_id, photo_type, file_path, thumbnail_path,
        gps_lat=gps_lat, gps_lng=gps_lng, notes=notes,
    )
    return {"data": evidence, "message": "Evidence uploaded"}


@router.post("/batch-sync")
async def batch_sync(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Batch sync offline photos. Accepts multipart form with files[] and metadata JSON."""
    form = await request.form()
    files = form.getlist("files")
    import json
    metadata_raw = form.get("metadata", "[]")
    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else []

    success = []
    failed = []

    for i, file in enumerate(files):
        try:
            meta = metadata[i] if i < len(metadata) else {}
            content = await file.read()
            file_path, thumbnail_path = await service.validate_and_save(
                content, file.filename, meta.get("appointment_id", 0), meta.get("photo_type", "EXCEPTION"),
            )
            evidence = await service.create_evidence(
                db, meta.get("appointment_id"), meta.get("photo_type", "EXCEPTION"),
                file_path, thumbnail_path,
                gps_lat=meta.get("gps_lat"), gps_lng=meta.get("gps_lng"),
            )
            success.append(evidence)
        except Exception as e:
            failed.append({"index": i, "error": str(e)})

    return {"success": success, "failed": failed}


@router.get("/{appointment_id}")
async def list_evidence(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
):
    evidence = await service.list_evidence(db, appointment_id)
    return {"data": evidence}
