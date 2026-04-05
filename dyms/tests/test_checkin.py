"""
Tests for check-in endpoints: /api/checkin/*

Covers:
  - Check-in by QR token
  - Safety acknowledgement enforcement
  - GPS geo_flag computation
  - Exception reporting
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import (
    SEED_USERS,
    SEED_FACILITY,
    FakeDBSession,
    FakeRedis,
    auth_header,
    make_appointment,
)


# ---------------------------------------------------------------------------
# Check-in by token
# ---------------------------------------------------------------------------


class TestCheckinByToken:
    """POST /api/checkin/token/{token}"""

    async def test_checkin_success(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
    ):
        """Valid token + safety_ack=True checks in the driver."""
        appt = make_appointment(
            id=10,
            status="AUTO_CONFIRMED",
            checkin_token="tok_valid_123",
            # Include facility geo columns that the JOIN returns
            geo_lat=SEED_FACILITY["geo_lat"],
            geo_lng=SEED_FACILITY["geo_lng"],
            geo_radius_m=SEED_FACILITY["geo_radius_m"],
        )
        checked_in_appt = {**appt, "status": "CHECKED_IN", "geo_flag": "OK"}

        # Queue: 1) SELECT appt + facility (for checkin_by_token service),
        #        2) UPDATE, 3) get_appointment_by_id after commit
        fake_db.rows.append([appt])         # SELECT ... FOR UPDATE
        fake_db.rows.append([{}])           # UPDATE
        fake_db.rows.append([checked_in_appt])  # get_appointment_by_id

        resp = await client.post(
            "/api/checkin/token/tok_valid_123",
            json={
                "safety_ack": True,
                "gps_lat": 40.7128,
                "gps_lng": -74.0060,
                "device_fingerprint": "fp_abc",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Checked in successfully"
        assert body["data"]["status"] == "CHECKED_IN"

    async def test_checkin_invalid_token(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
    ):
        """Unknown token returns 404."""
        fake_db.rows.append([])  # no appointment found

        resp = await client.post(
            "/api/checkin/token/tok_does_not_exist",
            json={"safety_ack": True},
        )

        assert resp.status_code == 404

    async def test_get_appointment_by_token(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
    ):
        """GET /api/checkin/token/{token} returns appointment info (no auth)."""
        appt = make_appointment(
            id=10,
            status="AUTO_CONFIRMED",
            checkin_token="tok_lookup",
            facility_name="Test Facility",
            facility_address="123 Dock St",
        )

        fake_db.rows.append([appt])

        resp = await client.get("/api/checkin/token/tok_lookup")

        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == 10

    async def test_get_appointment_by_invalid_token(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
    ):
        """GET with an unknown token returns 404."""
        fake_db.rows.append([])

        resp = await client.get("/api/checkin/token/tok_unknown")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Safety acknowledgement
# ---------------------------------------------------------------------------


class TestSafetyAcknowledgement:
    """Check-in must be rejected when safety_ack is False."""

    async def test_checkin_without_safety_ack_fails(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
    ):
        """safety_ack=False is rejected with 400."""
        resp = await client.post(
            "/api/checkin/token/tok_any",
            json={
                "safety_ack": False,
                "gps_lat": 40.7128,
                "gps_lng": -74.0060,
            },
        )

        assert resp.status_code == 400
        assert "safety" in resp.json()["detail"].lower()

    async def test_checkin_safety_ack_missing_defaults_false(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
    ):
        """Omitting safety_ack (defaults to False) also fails."""
        resp = await client.post(
            "/api/checkin/token/tok_any",
            json={},
        )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GPS geo_flag computation (unit tests for geo module)
# ---------------------------------------------------------------------------


class TestGeoFlagComputation:
    """Unit tests for app.utils.geo.compute_geo_flag."""

    def test_within_radius_returns_ok(self):
        from app.utils.geo import compute_geo_flag

        # Same coordinates -> distance 0 -> OK
        flag = compute_geo_flag(40.7128, -74.0060, 40.7128, -74.0060, 500)
        assert flag == "OK"

    def test_outside_radius_returns_out_of_range(self):
        from app.utils.geo import compute_geo_flag

        # ~111 km apart (1 degree latitude difference)
        flag = compute_geo_flag(41.7128, -74.0060, 40.7128, -74.0060, 500)
        assert flag == "OUT_OF_RANGE"

    def test_no_gps_returns_no_gps(self):
        from app.utils.geo import compute_geo_flag

        flag = compute_geo_flag(None, None, 40.7128, -74.0060, 500)
        assert flag == "NO_GPS"

    def test_partial_gps_returns_no_gps(self):
        from app.utils.geo import compute_geo_flag

        flag = compute_geo_flag(40.7128, None, 40.7128, -74.0060, 500)
        assert flag == "NO_GPS"

    def test_nearby_within_radius(self):
        from app.utils.geo import compute_geo_flag

        # Approximately 100m north of the facility
        flag = compute_geo_flag(40.7137, -74.0060, 40.7128, -74.0060, 500)
        assert flag == "OK"

    def test_just_outside_radius(self):
        from app.utils.geo import compute_geo_flag

        # Approximately 600m north -- outside 500m radius
        flag = compute_geo_flag(40.7182, -74.0060, 40.7128, -74.0060, 500)
        assert flag == "OUT_OF_RANGE"


class TestHaversine:
    """Unit tests for haversine_meters distance calculation."""

    def test_same_point_is_zero(self):
        from app.utils.geo import haversine_meters

        assert haversine_meters(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_known_distance(self):
        from app.utils.geo import haversine_meters

        # NYC to London approx 5570 km
        dist = haversine_meters(40.7128, -74.0060, 51.5074, -0.1278)
        assert 5_500_000 < dist < 5_600_000


# ---------------------------------------------------------------------------
# Exception report
# ---------------------------------------------------------------------------


class TestExceptionReport:
    """POST /api/checkin/exception"""

    async def test_report_exception_on_checked_in_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
    ):
        """Exception report on CHECKED_IN appointment succeeds."""
        appt = make_appointment(id=30, status="CHECKED_IN")

        # Queue: 1) get_appointment_by_id, 2) UPDATE status, 3) commit
        fake_db.rows.append([appt])
        fake_db.rows.append([{}])  # UPDATE

        resp = await client.post(
            "/api/checkin/exception",
            json={
                "appointment_id": 30,
                "exception_type": "seal_broken",
                "notes": "Seal was damaged on arrival",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Exception reported"
        assert body["appointment_id"] == 30

    async def test_exception_on_wrong_status_fails(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
    ):
        """Exception report on non-CHECKED_IN appointment returns 400."""
        appt = make_appointment(id=31, status="PENDING")

        fake_db.rows.append([appt])

        resp = await client.post(
            "/api/checkin/exception",
            json={
                "appointment_id": 31,
                "exception_type": "seal_broken",
            },
        )

        assert resp.status_code == 400

    async def test_exception_on_nonexistent_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
    ):
        """Exception report on unknown appointment returns 404."""
        fake_db.rows.append([])  # no appointment found

        resp = await client.post(
            "/api/checkin/exception",
            json={
                "appointment_id": 9999,
                "exception_type": "damage",
            },
        )

        assert resp.status_code == 404

    async def test_exception_requires_appointment_id(
        self,
        client: AsyncClient,
    ):
        """Missing appointment_id returns 422 validation error."""
        resp = await client.post(
            "/api/checkin/exception",
            json={"exception_type": "seal_broken"},
        )

        assert resp.status_code == 422
