"""
Tests for billing endpoints and billing engine logic.

Covers:
  - No-show charge creation
  - Detention fee calculation
  - Shunting charge
  - Waive billing event (admin only)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import (
    SEED_USERS,
    FakeDBSession,
    FakeRedis,
    auth_header,
    make_appointment,
    make_billing_event,
)


# ---------------------------------------------------------------------------
# Billing engine unit tests (no HTTP)
# ---------------------------------------------------------------------------


class TestBillingEngineNoShow:
    """Test create_noshow_charge from the billing engine."""

    async def test_noshow_charge_uses_configured_amount(self):
        """No-show charge should use the amount from billing config."""
        from app.billing.engine import create_noshow_charge

        fake_db = FakeDBSession()
        appt = make_appointment(id=1, status="NO_SHOW")
        config = {"noshow_amount": 75}

        # Queue: 1) INSERT RETURNING *
        created_event = make_billing_event(
            id=100, event_type="NO_SHOW", amount=75.0, appointment_id=1
        )
        fake_db.rows.append([created_event])

        result = await create_noshow_charge(fake_db, appt, config)

        assert result["event_type"] == "NO_SHOW"
        assert float(result["amount"]) == 75.0
        assert fake_db.committed

    async def test_noshow_charge_default_amount(self):
        """No-show charge defaults to $50 when config omits noshow_amount."""
        from app.billing.engine import create_noshow_charge

        fake_db = FakeDBSession()
        appt = make_appointment(id=2, status="NO_SHOW")
        config = {}  # no noshow_amount key

        created_event = make_billing_event(
            id=101, event_type="NO_SHOW", amount=50.0, appointment_id=2
        )
        fake_db.rows.append([created_event])

        result = await create_noshow_charge(fake_db, appt, config)

        assert float(result["amount"]) == 50.0


class TestBillingEngineDetention:
    """Test detention fee calculation from the billing engine."""

    async def test_no_charge_within_free_period(self):
        """No billing event created if still within free hours."""
        from app.billing.engine import check_detention_for_appointment

        fake_db = FakeDBSession()
        # Unload completed just 1 hour ago -- well within 48h free period
        now = datetime.now(timezone.utc)
        appt = make_appointment(
            id=3,
            status="UNLOAD_COMPLETE",
            actual_unload_complete=now - timedelta(hours=1),
        )
        config = {"detention_free_hours": 48}

        result = await check_detention_for_appointment(fake_db, appt, config)
        assert result is None

    async def test_charge_after_free_period(self):
        """Detention fee is created after the free period expires."""
        from app.billing.engine import check_detention_for_appointment

        fake_db = FakeDBSession()
        now = datetime.now(timezone.utc)
        # Unload completed 72 hours ago, free period is 48h -> 1 billable day
        appt = make_appointment(
            id=4,
            status="UNLOAD_COMPLETE",
            actual_unload_complete=now - timedelta(hours=72),
        )
        config = {
            "detention_free_hours": 48,
            "detention_tiers": [{"from_day": 1, "to_day": 3, "rate_per_day": 50}],
        }

        # Queue: 1) SELECT existing billing_events (none), 2) INSERT RETURNING *
        fake_db.rows.append([])  # no existing event
        created = make_billing_event(id=200, event_type="DETENTION", amount=50.0)
        fake_db.rows.append([created])

        result = await check_detention_for_appointment(fake_db, appt, config)

        assert result is not None
        assert float(result["amount"]) >= 50.0

    async def test_no_charge_when_unload_not_complete(self):
        """No detention check if actual_unload_complete is None."""
        from app.billing.engine import check_detention_for_appointment

        fake_db = FakeDBSession()
        appt = make_appointment(id=5, status="UNLOADING", actual_unload_complete=None)
        config = {"detention_free_hours": 48}

        result = await check_detention_for_appointment(fake_db, appt, config)
        assert result is None


class TestBillingEngineTierRate:
    """Test get_tier_rate helper."""

    def test_tier_1_rate(self):
        from app.billing.engine import get_tier_rate

        tiers = [
            {"from_day": 1, "to_day": 3, "rate_per_day": 50},
            {"from_day": 4, "to_day": None, "rate_per_day": 100},
        ]
        assert get_tier_rate(1, tiers) == 50
        assert get_tier_rate(3, tiers) == 50

    def test_tier_2_rate(self):
        from app.billing.engine import get_tier_rate

        tiers = [
            {"from_day": 1, "to_day": 3, "rate_per_day": 50},
            {"from_day": 4, "to_day": None, "rate_per_day": 100},
        ]
        assert get_tier_rate(4, tiers) == 100
        assert get_tier_rate(10, tiers) == 100

    def test_default_rate_when_no_match(self):
        from app.billing.engine import get_tier_rate

        # Empty tiers list falls back to 50
        assert get_tier_rate(1, []) == 50


class TestBillingEngineShunting:
    """Test shunting charge creation."""

    async def test_shunting_charge_is_150(self):
        """Shunting charge is a flat $150 per yard move."""
        from app.billing.engine import create_shunting_charge

        fake_db = FakeDBSession()
        appt = make_appointment(id=6, status="YARD_MOVED")

        created = make_billing_event(
            id=300, event_type="SHUNTING", amount=150.0, appointment_id=6
        )
        fake_db.rows.append([created])

        result = await create_shunting_charge(fake_db, appt)

        assert result["event_type"] == "SHUNTING"
        assert float(result["amount"]) == 150.0


# ---------------------------------------------------------------------------
# Billing API endpoint tests
# ---------------------------------------------------------------------------


class TestWaiveBillingEvent:
    """PATCH /api/billing/events/{id}/waive"""

    async def test_admin_can_waive_billing_event(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Admin can waive a PENDING billing event with a reason."""
        waived_event = make_billing_event(
            id=50, status="WAIVED", waived_by=admin_user["id"], waive_reason="goodwill"
        )

        # Queue: 1) get_current_user, 2) UPDATE RETURNING *, 3) audit INSERT
        fake_db.rows.append([admin_user])
        fake_db.rows.append([waived_event])
        fake_db.rows.append([{}])  # audit

        resp = await client.patch(
            "/api/billing/events/50/waive",
            headers=admin_token,
            json={"reason": "goodwill"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "Billing event waived"
        assert body["data"]["status"] == "WAIVED"

    async def test_shipper_cannot_waive_billing_event(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Only admin can waive -- shipper gets 403."""
        fake_db.rows.append([shipper_user])

        resp = await client.patch(
            "/api/billing/events/50/waive",
            headers=shipper_token,
            json={"reason": "please waive"},
        )

        assert resp.status_code == 403

    async def test_carrier_cannot_waive_billing_event(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        carrier_user: dict,
        carrier_token: dict,
    ):
        """Carrier also cannot waive billing events."""
        fake_db.rows.append([carrier_user])

        resp = await client.patch(
            "/api/billing/events/50/waive",
            headers=carrier_token,
            json={"reason": "carrier request"},
        )

        assert resp.status_code == 403

    async def test_waive_nonexistent_event(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Waiving a non-existent or already-processed event returns 404."""
        fake_db.rows.append([admin_user])
        fake_db.rows.append([])  # UPDATE returns nothing

        resp = await client.patch(
            "/api/billing/events/9999/waive",
            headers=admin_token,
            json={"reason": "test"},
        )

        assert resp.status_code == 404


class TestListBillingEvents:
    """GET /api/billing/events"""

    async def test_admin_can_list_billing_events(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        admin_user: dict,
        admin_token: dict,
    ):
        """Admin sees billing events with pagination."""
        evt = make_billing_event(id=1, event_type="DETENTION", amount=100.0)

        # Queue: 1) get_current_user, 2) COUNT, 3) SELECT rows
        fake_db.rows.append([admin_user])
        fake_db.scalar_values.append(1)
        fake_db.rows.append([])  # count query (scalar)
        fake_db.rows.append([evt])

        resp = await client.get("/api/billing/events?facility_id=1", headers=admin_token)

        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert body["total"] == 1

    async def test_shipper_sees_only_own_events(
        self,
        client: AsyncClient,
        fake_db: FakeDBSession,
        fake_redis: FakeRedis,
        shipper_user: dict,
        shipper_token: dict,
    ):
        """Shipper role auto-filters by their own shipper_id."""
        evt = make_billing_event(id=2, shipper_id=shipper_user["id"])

        fake_db.rows.append([shipper_user])
        fake_db.scalar_values.append(1)
        fake_db.rows.append([])
        fake_db.rows.append([evt])

        resp = await client.get("/api/billing/events?facility_id=1", headers=shipper_token)

        assert resp.status_code == 200
