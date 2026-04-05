"""Daily at 02:00: Clean up local photos older than 90 days (if backed up to cloud)."""

import os
import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import async_session
from app.config import settings

logger = structlog.get_logger()


async def cleanup_photos():
    if not settings.CLOUD_BACKUP_ENABLED:
        logger.info("photo_cleanup_skipped", reason="cloud backup disabled, retaining all local photos")
        return

    async with async_session() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        result = await db.execute(
            text("""
                SELECT id, file_path, thumbnail_path
                FROM appointment_evidence
                WHERE sync_status = 'SYNCED'
                  AND cloud_path IS NOT NULL
                  AND taken_at < :cutoff
                  AND litigation_hold = FALSE
            """),
            {"cutoff": cutoff},
        )
        old_photos = result.mappings().all()

        deleted = 0
        for photo in old_photos:
            for path in [photo["file_path"], photo.get("thumbnail_path")]:
                if path and os.path.exists(path):
                    os.remove(path)
                    deleted += 1

        logger.info("photo_cleanup_done", deleted_files=deleted)
