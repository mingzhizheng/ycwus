"""Email notification service using aiosmtplib and Jinja2 templates."""

import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
import structlog
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = structlog.get_logger()

# Template engine
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(template_dir))


async def send_email(to: str, subject: str, template_name: str, context: dict):
    """Render a template and send email."""
    try:
        template = jinja_env.get_template(template_name)
        html = template.render(**context)

        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg["Subject"] = f"[DYMS] {subject}"
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            use_tls=settings.SMTP_USE_TLS,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
        )
        logger.info("email_sent", to=to, subject=subject)
    except Exception as e:
        logger.error("email_send_failed", to=to, subject=subject, error=str(e))


async def notify_appointment_confirmed(appt: dict, shipper_email: str):
    await send_email(
        shipper_email,
        f"Appointment #{appt['id']} Confirmed",
        "appointment_confirmed.html",
        {"appt": appt},
    )


async def notify_noshow(appt: dict, shipper_email: str, penalty_amount: float):
    await send_email(
        shipper_email,
        f"No-Show: Appointment #{appt['id']}",
        "noshow_notice.html",
        {"appt": appt, "penalty_amount": penalty_amount},
    )


async def notify_detention_warning(appt: dict, shipper_email: str, free_period_end: str):
    await send_email(
        shipper_email,
        f"Detention Warning: Appointment #{appt['id']}",
        "detention_warning.html",
        {"appt": appt, "free_period_end": free_period_end},
    )


async def notify_exception(appt: dict, dispatcher_email: str):
    await send_email(
        dispatcher_email,
        f"Gate Exception: Appointment #{appt['id']}",
        "exception_alert.html",
        {"appt": appt},
    )
