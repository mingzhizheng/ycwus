from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def audit(
    db: AsyncSession,
    user_id: Optional[int],
    user_display: Optional[str],
    action: str,
    target: str,
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Write an audit log entry. All state changes, billing ops, waivers must be audited."""
    import json

    await db.execute(
        text("""
            INSERT INTO audit_log (user_id, user_display, action, target, payload, ip_address)
            VALUES (:user_id, :user_display, :action, :target, :payload, :ip_address)
        """),
        {
            "user_id": user_id,
            "user_display": user_display,
            "action": action,
            "target": target,
            "payload": json.dumps(payload) if payload else None,
            "ip_address": ip_address,
        },
    )
