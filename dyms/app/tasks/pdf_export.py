"""Daily at 04:00: Export appointment schedule PDF for today + tomorrow."""

import structlog

logger = structlog.get_logger()


async def export_daily_pdf():
    # Phase 2: Generate PDF using reportlab or weasyprint
    # Send to dispatcher email
    logger.info("pdf_export_skipped", reason="not implemented in Phase 1")
