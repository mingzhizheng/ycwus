"""
Shared fixtures for DYMS test suite.

Uses httpx.AsyncClient with ASGITransport to drive the FastAPI app
without needing a live server. Database and Redis dependencies are
overridden with lightweight fakes so tests run without infrastructure.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext

from app.auth.jwt import create_access_token, create_refresh_token
from app.config import settings

# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------


class FakeRedis:
    """In-memory dict that mimics the tiny slice of redis.asyncio used by DYMS."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, *, ex: int | None = None, nx: bool = False):
        if nx and key in self._store:
            return None
        self._store[key] = str(value)
        return True

    async def delete(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)

    async def close(self):
        self._store.clear()


# ---------------------------------------------------------------------------
# Fake async DB session
# ---------------------------------------------------------------------------


class FakeRow:
    """Wraps a dict so it behaves like a SQLAlchemy RowMapping."""

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def __iter__(self):
        return iter(self._data)

    def __contains__(self, key):
        return key in self._data


class FakeMappingResult:
    """Returned by result.mappings()."""

    def __init__(self, rows: list[dict]):
        self._rows = [FakeRow(r) for r in rows]

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeResult:
    """Mimics the object returned by ``session.execute(text(...))``."""

    def __init__(self, rows: list[dict] | None = None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def mappings(self):
        return FakeMappingResult(self._rows)

    def scalar(self):
        return self._scalar_value


class FakeDBSession:
    """
    Async DB session stub.

    Tests can pre-load ``session.rows`` with the data they want
    ``session.execute`` to return.  Each call to ``execute`` pops the
    first entry so sequential queries get different results.
    """

    def __init__(self):
        self.rows: list[list[dict]] = []          # queue of result-sets
        self.scalar_values: list = []              # queue of scalar returns
        self.committed = False
        self.executed_statements: list[str] = []   # for assertion inspection

    async def execute(self, stmt, params=None):
        query_text = str(stmt) if not isinstance(stmt, str) else stmt
        self.executed_statements.append(query_text)

        scalar_val = None
        if self.scalar_values:
            scalar_val = self.scalar_values.pop(0)

        if self.rows:
            return FakeResult(self.rows.pop(0), scalar_value=scalar_val)
        return FakeResult([], scalar_value=scalar_val)

    async def commit(self):
        self.committed = True

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USER_PASSWORD = "Test1234!"


def _make_user(
    id: int,
    username: str,
    role: str,
    display_name: str | None = None,
    facility_ids: list[int] | None = None,
) -> dict:
    return {
        "id": id,
        "username": username,
        "password_hash": pwd_context.hash(USER_PASSWORD),
        "role": role,
        "display_name": display_name or username.title(),
        "email": f"{username}@test.local",
        "phone": None,
        "company_name": "Test Co",
        "dmv_number": None,
        "facility_ids": facility_ids or [1],
        "is_active": True,
    }


SEED_USERS: dict[str, dict] = {
    "admin": _make_user(1, "admin", "admin", "Admin User"),
    "shipper": _make_user(2, "shipper1", "shipper", "Shipper One"),
    "carrier": _make_user(3, "carrier1", "carrier", "Carrier One"),
    "warehouse_staff": _make_user(4, "warehouse1", "warehouse_staff", "WH Staff"),
    "dispatcher": _make_user(5, "dispatcher1", "dispatcher", "Dispatcher One"),
    "driver": _make_user(6, "driver1", "driver", "Driver One"),
}

SEED_FACILITY = {
    "id": 1,
    "code": "FAC1",
    "name": "Test Facility",
    "address": "123 Dock St",
    "timezone": "America/New_York",
    "geo_lat": 40.7128,
    "geo_lng": -74.0060,
    "geo_radius_m": 500,
    "is_active": True,
}


def make_appointment(
    id: int = 1,
    status: str = "PENDING",
    shipper_id: int = 2,
    facility_id: int = 1,
    **overrides,
) -> dict:
    """Return a dict that looks like an appointment row."""
    base = {
        "id": id,
        "facility_id": facility_id,
        "asn_id": None,
        "shipper_id": shipper_id,
        "carrier_id": None,
        "appointment_type": "LIVE",
        "carrier_type": "own",
        "platform_name": None,
        "platform_order_id": None,
        "status": status,
        "scheduled_start": datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        "scheduled_end": datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc),
        "buffer_minutes": 30,
        "actual_arrival": None,
        "actual_dock_start": None,
        "actual_unload_start": None,
        "actual_unload_complete": None,
        "actual_pickup": None,
        "actual_yard_move_at": None,
        "dock_id": None,
        "yard_spot_id": None,
        "driver_name": "Test Driver",
        "driver_phone": "555-0100",
        "truck_plate": "ABC123",
        "checkin_token": "tok_test_abc123",
        "checkin_lat": None,
        "checkin_lng": None,
        "geo_flag": "OK",
        "safety_ack_at": None,
        "device_fingerprint": None,
        "cargo_type_actual": None,
        "cargo_type_mismatch": False,
        "bol_number": "BOL001",
        "bol_file_path": None,
        "actual_unload_duration": None,
        "yard_move_count": 0,
        "reschedule_count": 0,
        "ltl_master_pro": None,
        "created_by": shipper_id,
        "confirmed_by": None,
        "cancelled_by": None,
        "cancel_reason": None,
        "created_at": datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc),
        # Joined columns often present in query results
        "shipper_name": "Shipper One",
        "dock_code": None,
        "yard_code": None,
    }
    base.update(overrides)
    return base


def make_billing_event(
    id: int = 1,
    facility_id: int = 1,
    appointment_id: int = 1,
    shipper_id: int = 2,
    event_type: str = "DETENTION",
    amount: float = 50.0,
    status: str = "PENDING",
    **overrides,
) -> dict:
    """Return a dict that looks like a billing_events row."""
    base = {
        "id": id,
        "facility_id": facility_id,
        "appointment_id": appointment_id,
        "shipper_id": shipper_id,
        "event_type": event_type,
        "amount": amount,
        "currency": "USD",
        "status": status,
        "free_period_end": None,
        "billable_start": None,
        "billable_end": None,
        "waived_by": None,
        "waive_reason": None,
        "liable_party": "shipper",
        "liable_note": None,
        "invoice_id": None,
        "created_at": datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        "shipper_name": "Shipper One",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture()
def fake_db() -> FakeDBSession:
    return FakeDBSession()


@pytest_asyncio.fixture()
async def client(fake_db: FakeDBSession, fake_redis: FakeRedis) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an httpx AsyncClient wired to the FastAPI app with DB and Redis
    dependencies replaced by fakes.
    """
    from app.database import get_db
    from app.redis_client import get_redis
    from app.main import app

    async def override_get_db():
        yield fake_db

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user() -> dict:
    return SEED_USERS["admin"]


@pytest.fixture()
def shipper_user() -> dict:
    return SEED_USERS["shipper"]


@pytest.fixture()
def carrier_user() -> dict:
    return SEED_USERS["carrier"]


@pytest.fixture()
def warehouse_staff_user() -> dict:
    return SEED_USERS["warehouse_staff"]


@pytest.fixture()
def dispatcher_user() -> dict:
    return SEED_USERS["dispatcher"]


@pytest.fixture()
def driver_user() -> dict:
    return SEED_USERS["driver"]


def make_token(user: dict) -> str:
    """Create a valid JWT access token for the given seed user dict."""
    return create_access_token(
        user_id=user["id"],
        role=user["role"],
        facility_ids=user.get("facility_ids", [1]),
    )


def auth_header(user: dict) -> dict[str, str]:
    """Return an Authorization header dict for the given user."""
    return {"Authorization": f"Bearer {make_token(user)}"}


@pytest.fixture()
def admin_token(admin_user) -> dict[str, str]:
    return auth_header(admin_user)


@pytest.fixture()
def shipper_token(shipper_user) -> dict[str, str]:
    return auth_header(shipper_user)


@pytest.fixture()
def carrier_token(carrier_user) -> dict[str, str]:
    return auth_header(carrier_user)


@pytest.fixture()
def warehouse_staff_token(warehouse_staff_user) -> dict[str, str]:
    return auth_header(warehouse_staff_user)


@pytest.fixture()
def dispatcher_token(dispatcher_user) -> dict[str, str]:
    return auth_header(dispatcher_user)


@pytest.fixture()
def driver_token(driver_user) -> dict[str, str]:
    return auth_header(driver_user)
