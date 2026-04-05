"""
Tests for authentication endpoints: /api/auth/*

These tests verify login, token refresh, unauthorized access,
and role-based access control.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    SEED_USERS,
    USER_PASSWORD,
    FakeDBSession,
    FakeRedis,
    auth_header,
    make_token,
    pwd_context,
)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    """POST /api/auth/login"""

    async def test_login_valid_credentials(
        self, client: AsyncClient, fake_db: FakeDBSession, fake_redis: FakeRedis
    ):
        """Successful login returns access + refresh tokens and user info."""
        user = SEED_USERS["admin"]
        # The login endpoint executes one SELECT query
        fake_db.rows.append([user])

        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": USER_PASSWORD},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["username"] == "admin"
        assert body["user"]["role"] == "admin"

    async def test_login_invalid_username(
        self, client: AsyncClient, fake_db: FakeDBSession
    ):
        """Unknown username returns 401."""
        fake_db.rows.append([])  # no user found

        resp = await client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "whatever"},
        )
        assert resp.status_code == 401

    async def test_login_wrong_password(
        self, client: AsyncClient, fake_db: FakeDBSession
    ):
        """Correct username but wrong password returns 401."""
        user = SEED_USERS["shipper"]
        fake_db.rows.append([user])

        resp = await client.post(
            "/api/auth/login",
            json={"username": "shipper1", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    async def test_login_inactive_user(
        self, client: AsyncClient, fake_db: FakeDBSession
    ):
        """Deactivated user cannot log in."""
        user = {**SEED_USERS["shipper"], "is_active": False}
        fake_db.rows.append([user])

        resp = await client.post(
            "/api/auth/login",
            json={"username": "shipper1", "password": USER_PASSWORD},
        )
        assert resp.status_code == 401

    async def test_login_returns_correct_user_fields(
        self, client: AsyncClient, fake_db: FakeDBSession, fake_redis: FakeRedis
    ):
        """Login response includes id, username, role, display_name, email."""
        user = SEED_USERS["shipper"]
        fake_db.rows.append([user])

        resp = await client.post(
            "/api/auth/login",
            json={"username": "shipper1", "password": USER_PASSWORD},
        )

        assert resp.status_code == 200
        u = resp.json()["user"]
        assert u["id"] == user["id"]
        assert u["display_name"] == user["display_name"]
        assert u["email"] == user["email"]


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    """POST /api/auth/refresh"""

    async def test_refresh_valid_token(
        self, client: AsyncClient, fake_redis: FakeRedis
    ):
        """Valid refresh token yields a new access token."""
        from app.auth.jwt import create_refresh_token

        token, jti = create_refresh_token(user_id=1)
        # Simulate that the refresh token was stored in Redis
        await fake_redis.set(f"refresh:1:{jti}", "1", ex=86400)

        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_refresh_expired_or_revoked(
        self, client: AsyncClient, fake_redis: FakeRedis
    ):
        """Refresh token not present in Redis is rejected."""
        from app.auth.jwt import create_refresh_token

        token, jti = create_refresh_token(user_id=1)
        # Do NOT store in Redis -- simulates revoked / expired

        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": token},
        )
        assert resp.status_code == 401

    async def test_refresh_with_access_token_rejected(
        self, client: AsyncClient
    ):
        """An access token cannot be used as a refresh token."""
        access = make_token(SEED_USERS["admin"])

        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": access},
        )
        assert resp.status_code == 401

    async def test_refresh_with_garbage_string(
        self, client: AsyncClient
    ):
        """Completely invalid JWT string is rejected."""
        resp = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "not-a-jwt-at-all"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unauthorized access
# ---------------------------------------------------------------------------


class TestUnauthorizedAccess:
    """Endpoints that require auth must reject unauthenticated requests."""

    async def test_no_token(self, client: AsyncClient):
        """Missing Authorization header returns 422 or 401."""
        resp = await client.get("/api/auth/me")
        # FastAPI returns 422 when a required Header is missing
        assert resp.status_code in (401, 422)

    async def test_malformed_token(self, client: AsyncClient):
        """Malformed bearer token returns 401."""
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert resp.status_code == 401

    async def test_bearer_prefix_missing(self, client: AsyncClient):
        """Token without 'Bearer ' prefix is rejected."""
        token = make_token(SEED_USERS["admin"])
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": token},  # no "Bearer " prefix
        )
        assert resp.status_code == 401

    async def test_empty_bearer_value(self, client: AsyncClient):
        """Bearer with empty value is rejected."""
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


class TestRBAC:
    """Verify that role restrictions on endpoints are enforced."""

    async def test_admin_can_list_users(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Admin role can access GET /api/auth/users."""
        # get_current_user does a DB lookup + redis blacklist check
        fake_db.rows.append([admin_user])  # user lookup
        fake_db.rows.append([admin_user])  # list_users query

        resp = await client.get("/api/auth/users", headers=admin_token)
        assert resp.status_code == 200

    async def test_shipper_cannot_list_users(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Shipper role is forbidden from GET /api/auth/users."""
        fake_db.rows.append([shipper_user])  # user lookup in get_current_user

        resp = await client.get("/api/auth/users", headers=shipper_token)
        assert resp.status_code == 403

    async def test_carrier_cannot_create_users(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        carrier_user: dict,
        carrier_token: dict,
    ):
        """Only admin can POST /api/auth/users."""
        fake_db.rows.append([carrier_user])  # user lookup

        resp = await client.post(
            "/api/auth/users",
            headers=carrier_token,
            json={
                "username": "newguy",
                "password": "Abc12345!",
                "display_name": "New Guy",
                "role": "shipper",
            },
        )
        assert resp.status_code == 403

    async def test_dispatcher_can_list_users(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        dispatcher_user: dict,
        dispatcher_token: dict,
    ):
        """Dispatcher role can access GET /api/auth/users."""
        fake_db.rows.append([dispatcher_user])  # user lookup
        fake_db.rows.append([dispatcher_user])  # list_users query

        resp = await client.get("/api/auth/users", headers=dispatcher_token)
        assert resp.status_code == 200

    async def test_warehouse_staff_cannot_list_users(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        warehouse_staff_user: dict,
        warehouse_staff_token: dict,
    ):
        """Warehouse staff is forbidden from GET /api/auth/users."""
        fake_db.rows.append([warehouse_staff_user])

        resp = await client.get("/api/auth/users", headers=warehouse_staff_token)
        assert resp.status_code == 403
