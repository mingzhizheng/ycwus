import json

from fastapi import APIRouter, Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.redis_client import get_redis
from app.config import settings
from app.middleware.rate_limit import limiter
from app.auth.jwt import create_access_token, create_refresh_token, decode_token
from app.auth.schemas import LoginRequest, TokenResponse, RefreshRequest, UserCreate, UserResponse
from app.auth.dependencies import get_current_user, require_role

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id, username, password_hash, role, display_name, email, facility_ids, is_active FROM users WHERE username = :u"),
        {"u": data.username},
    )
    user = result.mappings().first()

    if not user or not user["is_active"]:
        raise HTTPException(401, "Invalid username or password")

    if not pwd_context.verify(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password")

    facility_ids = json.loads(user["facility_ids"]) if isinstance(user["facility_ids"], str) else user["facility_ids"]

    access_token = create_access_token(user["id"], user["role"], facility_ids)
    refresh_token, refresh_jti = create_refresh_token(user["id"])

    # Store refresh token in Redis
    redis = await get_redis()
    await redis.set(
        f"refresh:{user['id']}:{refresh_jti}",
        "1",
        ex=settings.JWT_REFRESH_EXPIRE_DAYS * 86400,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"],
            "email": user["email"],
        },
    )


@router.post("/refresh")
async def refresh(data: RefreshRequest):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(401, "Invalid refresh token")

    user_id = int(payload["sub"])
    jti = payload["jti"]

    redis = await get_redis()
    exists = await redis.get(f"refresh:{user_id}:{jti}")
    if not exists:
        raise HTTPException(401, "Refresh token expired or revoked")

    access_token = create_access_token(user_id, payload.get("role", ""), [])
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    return {"message": "Logged out"}


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {"data": user}


@router.get("/users")
async def list_users(
    user=require_role("admin", "dispatcher"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("SELECT id, username, display_name, role, email, phone, company_name, is_active, created_at FROM users ORDER BY id")
    )
    users = [dict(row) for row in result.mappings().all()]
    return {"data": users}


@router.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    user=require_role("admin"),
    db: AsyncSession = Depends(get_db),
):
    password_hash = pwd_context.hash(data.password)
    facility_ids_json = json.dumps(data.facility_ids)

    result = await db.execute(
        text("""
            INSERT INTO users (username, password_hash, display_name, role, email, phone, company_name, dmv_number, facility_ids)
            VALUES (:username, :password_hash, :display_name, :role, :email, :phone, :company_name, :dmv_number, :facility_ids)
            RETURNING id, username, display_name, role, email, phone, company_name, is_active
        """),
        {
            "username": data.username,
            "password_hash": password_hash,
            "display_name": data.display_name,
            "role": data.role,
            "email": data.email,
            "phone": data.phone,
            "company_name": data.company_name,
            "dmv_number": data.dmv_number,
            "facility_ids": facility_ids_json,
        },
    )
    await db.commit()
    new_user = dict(result.mappings().first())
    return new_user
