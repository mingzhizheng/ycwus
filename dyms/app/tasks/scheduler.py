"""
APScheduler task registration with error/missed listeners.
All times use facility timezone from settings.
"""

import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED

logger = structlog.get_logger()
scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": 300})


def job_error_listener(event):
    logger.error(
        "scheduled_job_failed",
        job_id=event.job_id,
        exception=str(event.exception),
    )


def job_missed_listener(event):
    logger.warning("scheduled_job_missed", job_id=event.job_id)


def register_tasks():
    scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
    scheduler.add_listener(job_missed_listener, EVENT_JOB_MISSED)

    # Every 5 minutes: NO_SHOW detection
    scheduler.add_job(
        _run_noshow_check, "interval", minutes=5, id="noshow_check",
        replace_existing=True,
    )

    # Every hour: Detention fee calculation
    scheduler.add_job(
        _run_detention_check, "interval", hours=1, id="detention_check",
        replace_existing=True,
    )

    # Daily at 17:00 ET (22:00 UTC): Overnight lock
    scheduler.add_job(
        _run_overnight_lock, "cron", hour=22, minute=0, id="overnight_lock",
        replace_existing=True,
    )

    # Daily at 06:00 ET (11:00 UTC): Auto-schedule drops
    scheduler.add_job(
        _run_auto_drops, "cron", hour=11, minute=0, id="auto_drops",
        replace_existing=True,
    )

    # Daily at 02:00 ET (07:00 UTC): Photo cleanup
    scheduler.add_job(
        _run_photo_cleanup, "cron", hour=7, minute=0, id="photo_cleanup",
        replace_existing=True,
    )

    # Daily at 04:00 ET (09:00 UTC): PDF export
    scheduler.add_job(
        _run_pdf_export, "cron", hour=9, minute=0, id="pdf_export",
        replace_existing=True,
    )

    # Hourly: Cloud backup
    scheduler.add_job(
        _run_cloud_backup, "interval", hours=1, id="cloud_backup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler_started", jobs=len(scheduler.get_jobs()))


def shutdown_tasks():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_shutdown")


# Wrappers that create DB sessions per job execution
async def _run_noshow_check():
    from app.tasks.noshow_check import check_noshow
    try:
        await check_noshow()
    except Exception as e:
        logger.exception("noshow_check_error", error=str(e))
        raise


async def _run_detention_check():
    from app.tasks.detention_check import check_detention
    try:
        await check_detention()
    except Exception as e:
        logger.exception("detention_check_error", error=str(e))
        raise


async def _run_overnight_lock():
    from app.tasks.overnight_lock import check_overnight
    try:
        await check_overnight()
    except Exception as e:
        logger.exception("overnight_lock_error", error=str(e))
        raise


async def _run_auto_drops():
    from app.tasks.auto_drops import auto_schedule_drops
    try:
        await auto_schedule_drops()
    except Exception as e:
        logger.exception("auto_drops_error", error=str(e))
        raise


async def _run_photo_cleanup():
    from app.tasks.photo_cleanup import cleanup_photos
    try:
        await cleanup_photos()
    except Exception as e:
        logger.exception("photo_cleanup_error", error=str(e))
        raise


async def _run_pdf_export():
    from app.tasks.pdf_export import export_daily_pdf
    try:
        await export_daily_pdf()
    except Exception as e:
        logger.exception("pdf_export_error", error=str(e))
        raise


async def _run_cloud_backup():
    from app.tasks.cloud_backup import backup_to_cloud
    try:
        await backup_to_cloud()
    except Exception as e:
        logger.exception("cloud_backup_error", error=str(e))
        raise
