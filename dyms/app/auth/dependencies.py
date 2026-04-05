from fastapi import Depends, HTTPException, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.jwt import decode_token
from app.redis_client import get_redis


async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header")

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(401, "Token invalid or expired")

    # Check blacklist
    jti = payload.get("jti")
    if jti:
        blacklisted = await redis.get(f"blacklist:{jti}")
        if blacklisted:
            raise HTTPException(401, "Token has been revoked")

    user_id = int(payload["sub"])
    result = await db.execute(
        text("SELECT id, username, role, display_name, email, phone, company_name, facility_ids, is_active FROM users WHERE id = :id"),
        {"id": user_id},
    )
    user = result.mappings().first()
    if not user or not user["is_active"]:
        raise HTTPException(401, "User not found or deactivated")

    return dict(user)


def require_role(*allowed_roles):
    async def checker(user=Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return Depends(checker)
