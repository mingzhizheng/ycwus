import os
import uuid
import io
from datetime import datetime

from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


async def validate_and_save(
    content: bytes,
    filename: str,
    appointment_id: int,
    photo_type: str,
    facility_id: int = 1,
) -> tuple[str, str | None]:
    """Validate file, save original + thumbnail. Returns (file_path, thumbnail_path)."""
    try:
        import magic
        mime = magic.from_buffer(content, mime=True)
        if mime not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Unsupported file type: {mime}")
    except ImportError:
        pass  # python-magic not available in dev

    # Determine paths
    now = datetime.utcnow()
    subdir = f"{facility_id}/{now.strftime('%Y-%m')}"
    ext = os.path.splitext(filename)[1] or ".jpg"
    unique_name = f"{appointment_id}_{photo_type}_{uuid.uuid4().hex[:8]}{ext}"

    evidence_dir = os.path.join(settings.UPLOAD_DIR, "evidence", subdir)
    thumb_dir = os.path.join(settings.UPLOAD_DIR, "thumbnails", subdir)
    os.makedirs(evidence_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)

    file_path = os.path.join(evidence_dir, unique_name)
    thumbnail_path = None

    # Save original
    with open(file_path, "wb") as f:
        f.write(content)

    # Generate thumbnail for images
    if ext.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        try:
            img = Image.open(io.BytesIO(content))
            img.thumbnail((300, 300))
            thumb_name = f"thumb_{unique_name}"
            thumbnail_path = os.path.join(thumb_dir, thumb_name)
            img.save(thumbnail_path)
        except Exception:
            pass

    return file_path, thumbnail_path


async def create_evidence(
    db: AsyncSession,
    appointment_id: int,
    photo_type: str,
    file_path: str,
    thumbnail_path: str | None = None,
    taken_by: int | None = None,
    gps_lat: float | None = None,
    gps_lng: float | None = None,
    notes: str | None = None,
) -> dict:
    result = await db.execute(
        text("""
            INSERT INTO appointment_evidence (appointment_id, photo_type, file_path, thumbnail_path, taken_by, gps_lat, gps_lng, notes)
            VALUES (:appointment_id, :photo_type, :file_path, :thumbnail_path, :taken_by, :gps_lat, :gps_lng, :notes)
            RETURNING *
        """),
        {
            "appointment_id": appointment_id,
            "photo_type": photo_type,
            "file_path": file_path,
            "thumbnail_path": thumbnail_path,
            "taken_by": taken_by,
            "gps_lat": gps_lat,
            "gps_lng": gps_lng,
            "notes": notes,
        },
    )
    await db.commit()
    return dict(result.mappings().first())


async def list_evidence(db: AsyncSession, appointment_id: int) -> list:
    result = await db.execute(
        text("SELECT * FROM appointment_evidence WHERE appointment_id = :id ORDER BY taken_at"),
        {"id": appointment_id},
    )
    return [dict(r) for r in result.mappings().all()]
