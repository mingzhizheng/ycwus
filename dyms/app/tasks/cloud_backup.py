"""Hourly: Backup local evidence photos to cloud storage (S3)."""

import structlog

from app.config import settings

logger = structlog.get_logger()


async def backup_to_cloud():
    if not settings.CLOUD_BACKUP_ENABLED:
        return

    # Phase 2: Implement S3 upload for evidence with sync_status = 'LOCAL'
    logger.info("cloud_backup_skipped", reason="not implemented in Phase 1")
