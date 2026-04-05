"""
Tests for appointment endpoints: /api/appointments/*

These tests verify CRUD operations on appointments including creation,
listing, detail retrieval, and cancellation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import (
    SEED_USERS,
    FakeDBSession,
    FakeRedis,
    auth_header,
    make_appointment,
)


# ---------------------------------------------------------------------------
# Create appointment
# ---------------------------------------------------------------------------


class TestCreateAppointment:
    """POST /api/appointments"""

    async def test_shipper_can_create_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Shipper role can create an appointment and gets back the new record."""
        created_appt = make_appointment(id=10, status="PENDING", shipper_id=shipper_user["id"])

        # Queue: 1) get_current_user lookup, 2) INSERT RETURNING *
        fake_db.rows.append([shipper_user])
        fake_db.rows.append([created_appt])

        resp = await client.post(
            "/api/appointments",
            headers=shipper_token,
            json={
                "facility_id": 1,
                "appointment_type": "LIVE",
                "carrier_type": "own",
                "scheduled_start": "2026-04-10T09:00:00Z",
                "driver_name": "Test Driver",
                "truck_plate": "ABC123",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Appointment created"
        assert body["data"]["id"] == 10
        assert body["data"]["status"] == "PENDING"

    async def test_admin_can_create_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Admin role can create appointments on behalf of others."""
        created_appt = make_appointment(id=11, status="PENDING", shipper_id=admin_user["id"])

        fake_db.rows.append([admin_user])
        fake_db.rows.append([created_appt])

        resp = await client.post(
            "/api/appointments",
            headers=admin_token,
            json={
                "facility_id": 1,
                "appointment_type": "DROP",
                "carrier_type": "own",
                "scheduled_start": "2026-04-11T10:00:00Z",
            },
        )

        assert resp.status_code == 200

    async def test_warehouse_staff_cannot_create_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        warehouse_staff_user: dict,
        warehouse_staff_token: dict,
    ):
        """Warehouse staff is not allowed to create appointments."""
        fake_db.rows.append([warehouse_staff_user])

        resp = await client.post(
            "/api/appointments",
            headers=warehouse_staff_token,
            json={
                "facility_id": 1,
                "appointment_type": "LIVE",
                "scheduled_start": "2026-04-10T09:00:00Z",
            },
        )

        assert resp.status_code == 403

    async def test_create_appointment_missing_required_fields(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Omitting required fields returns a 422 validation error."""
        fake_db.rows.append([shipper_user])

        resp = await client.post(
            "/api/appointments",
            headers=shipper_token,
            json={
                "facility_id": 1,
                # Missing appointment_type and scheduled_start
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List appointments
# ---------------------------------------------------------------------------


class TestListAppointments:
    """GET /api/appointments"""

    async def test_list_appointments_returns_paginated_results(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Listing appointments returns data with pagination metadata."""
        appt1 = make_appointment(id=1, status="PENDING")
        appt2 = make_appointment(id=2, status="AUTO_CONFIRMED")

        # Queue: 1) get_current_user, 2) COUNT(*), 3) SELECT rows
        fake_db.rows.append([admin_user])
        fake_db.scalar_values.append(2)
        fake_db.rows.append([])  # COUNT query returns via scalar, rows unused
        fake_db.rows.append([appt1, appt2])

        resp = await client.get("/api/appointments", headers=admin_token)

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["total"] == 2
        assert body["page"] == 1

    async def test_shipper_sees_only_own_appointments(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Shipper role filters by shipper_id automatically."""
        appt = make_appointment(id=5, shipper_id=shipper_user["id"])

        fake_db.rows.append([shipper_user])
        fake_db.scalar_values.append(1)
        fake_db.rows.append([])
        fake_db.rows.append([appt])

        resp = await client.get("/api/appointments", headers=shipper_token)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1

    async def test_list_appointments_with_status_filter(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Filtering by status query parameter is accepted."""
        fake_db.rows.append([admin_user])
        fake_db.scalar_values.append(0)
        fake_db.rows.append([])
        fake_db.rows.append([])

        resp = await client.get(
            "/api/appointments?status=CHECKED_IN", headers=admin_token
        )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Get appointment detail
# ---------------------------------------------------------------------------


class TestGetAppointmentDetail:
    """GET /api/appointments/{id}"""

    async def test_get_existing_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Fetching an existing appointment returns full detail."""
        appt = make_appointment(id=42, status="AUTO_CONFIRMED")

        # Queue: 1) get_current_user, 2) SELECT appointment
        fake_db.rows.append([admin_user])
        fake_db.rows.append([appt])

        resp = await client.get("/api/appointments/42", headers=admin_token)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == 42
        assert body["data"]["status"] == "AUTO_CONFIRMED"

    async def test_get_nonexistent_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Fetching a non-existent appointment returns 404."""
        fake_db.rows.append([admin_user])
        fake_db.rows.append([])  # no matching row

        resp = await client.get("/api/appointments/9999", headers=admin_token)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cancel appointment
# ---------------------------------------------------------------------------


class TestCancelAppointment:
    """PATCH /api/appointments/{id}/cancel"""

    async def test_shipper_can_cancel_pending_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Shipper can cancel their own PENDING appointment."""
        appt = make_appointment(id=20, status="PENDING", shipper_id=shipper_user["id"])
        cancelled_appt = {**appt, "status": "CANCELLED", "cancel_reason": "changed plans"}

        # Queue: 1) get_current_user, 2) SELECT FOR UPDATE, 3) audit INSERT,
        #        4) get_appointment after commit
        fake_db.rows.append([shipper_user])
        fake_db.rows.append([appt])
        fake_db.rows.append([{}])         # audit insert
        fake_db.rows.append([cancelled_appt])

        resp = await client.patch(
            "/api/appointments/20/cancel?reason=changed+plans",
            headers=shipper_token,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Appointment cancelled"
        assert body["data"]["status"] == "CANCELLED"

    async def test_cancel_nonexistent_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Cancelling a non-existent appointment returns 404."""
        fake_db.rows.append([shipper_user])
        fake_db.rows.append([])  # no appointment found

        resp = await client.patch(
            "/api/appointments/9999/cancel",
            headers=shipper_token,
        )

        assert resp.status_code == 404

    async def test_carrier_can_cancel_confirmed_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        carrier_user: dict,
        carrier_token: dict,
    ):
        """Carrier can cancel an AUTO_CONFIRMED appointment."""
        appt = make_appointment(id=21, status="AUTO_CONFIRMED", carrier_id=carrier_user["id"])
        cancelled = {**appt, "status": "CANCELLED"}

        fake_db.rows.append([carrier_user])
        fake_db.rows.append([appt])
        fake_db.rows.append([{}])         # audit
        fake_db.rows.append([cancelled])

        resp = await client.patch(
            "/api/appointments/21/cancel",
            headers=carrier_token,
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "CANCELLED"

    async def test_warehouse_staff_cannot_cancel_appointment(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        warehouse_staff_user: dict,
        warehouse_staff_token: dict,
    ):
        """Warehouse staff cannot cancel appointments (not in allowed roles)."""
        appt = make_appointment(id=22, status="PENDING")

        fake_db.rows.append([warehouse_staff_user])
        fake_db.rows.append([appt])  # SELECT FOR UPDATE

        resp = await client.patch(
            "/api/appointments/22/cancel",
            headers=warehouse_staff_token,
        )

        # State machine rejects: warehouse_staff not in cancel roles
        assert resp.status_code == 400
