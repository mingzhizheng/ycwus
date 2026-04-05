"""
Tests for the appointment state machine: app.appointments.state_machine

These are pure unit tests -- no HTTP, no DB. They exercise the transition
matrix, role restrictions, and edge cases directly.
"""

from __future__ import annotations

import pytest

from app.appointments.state_machine import (
    TRANSITIONS,
    get_allowed_transitions,
    get_transition,
    is_valid_transition,
)


# ---------------------------------------------------------------------------
# Valid transitions
# ---------------------------------------------------------------------------


class TestValidTransitions:
    """Verify that each defined transition is reachable by the right roles."""

    def test_pending_to_auto_confirmed(self):
        assert is_valid_transition("PENDING", "AUTO_CONFIRMED", "system")
        assert is_valid_transition("PENDING", "AUTO_CONFIRMED", "admin")
        assert is_valid_transition("PENDING", "AUTO_CONFIRMED", "dispatcher")

    def test_auto_confirmed_to_checked_in(self):
        assert is_valid_transition("AUTO_CONFIRMED", "CHECKED_IN", "driver")
        assert is_valid_transition("AUTO_CONFIRMED", "CHECKED_IN", "warehouse_staff")
        assert is_valid_transition("AUTO_CONFIRMED", "CHECKED_IN", "dispatcher")
        assert is_valid_transition("AUTO_CONFIRMED", "CHECKED_IN", "admin")

    def test_checked_in_to_dock_assigned(self):
        assert is_valid_transition("CHECKED_IN", "DOCK_ASSIGNED", "dispatcher")
        assert is_valid_transition("CHECKED_IN", "DOCK_ASSIGNED", "admin")

    def test_dock_assigned_to_unloading(self):
        assert is_valid_transition("DOCK_ASSIGNED", "UNLOADING", "warehouse_staff")
        assert is_valid_transition("DOCK_ASSIGNED", "UNLOADING", "dispatcher")

    def test_unloading_to_unload_complete(self):
        assert is_valid_transition("UNLOADING", "UNLOAD_COMPLETE", "warehouse_staff")

    def test_unload_complete_to_yard_moved(self):
        assert is_valid_transition("UNLOAD_COMPLETE", "YARD_MOVED", "warehouse_staff")

    def test_unload_complete_to_awaiting_pickup(self):
        assert is_valid_transition("UNLOAD_COMPLETE", "AWAITING_PICKUP", "dispatcher")

    def test_yard_moved_to_awaiting_pickup(self):
        assert is_valid_transition("YARD_MOVED", "AWAITING_PICKUP", "dispatcher")

    def test_awaiting_pickup_to_picked_up(self):
        assert is_valid_transition("AWAITING_PICKUP", "PICKED_UP", "warehouse_staff")

    def test_picked_up_to_closed(self):
        assert is_valid_transition("PICKED_UP", "CLOSED", "admin")
        # system is always implicitly allowed (see is_valid_transition logic)
        assert is_valid_transition("PICKED_UP", "CLOSED", "system")

    def test_checked_in_to_exception_at_gate(self):
        assert is_valid_transition("CHECKED_IN", "EXCEPTION_AT_GATE", "driver")
        assert is_valid_transition("CHECKED_IN", "EXCEPTION_AT_GATE", "warehouse_staff")

    def test_auto_confirmed_to_no_show(self):
        """System can mark no-show after tolerance window."""
        assert is_valid_transition("AUTO_CONFIRMED", "NO_SHOW", "system")

    def test_no_show_override_to_checked_in(self):
        """Dispatcher / admin can override a no-show."""
        assert is_valid_transition("NO_SHOW", "CHECKED_IN", "dispatcher")
        assert is_valid_transition("NO_SHOW", "CHECKED_IN", "admin")

    def test_exception_at_gate_override_to_checked_in(self):
        assert is_valid_transition("EXCEPTION_AT_GATE", "CHECKED_IN", "dispatcher")
        assert is_valid_transition("EXCEPTION_AT_GATE", "CHECKED_IN", "admin")


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


class TestInvalidTransitions:
    """Transitions that should be rejected by the state machine."""

    def test_pending_to_unloading_not_allowed(self):
        """Cannot jump from PENDING directly to UNLOADING."""
        assert not is_valid_transition("PENDING", "UNLOADING", "admin")
        assert not is_valid_transition("PENDING", "UNLOADING", "system")

    def test_pending_to_dock_assigned_not_allowed(self):
        assert not is_valid_transition("PENDING", "DOCK_ASSIGNED", "dispatcher")

    def test_checked_in_to_closed_not_allowed(self):
        """Cannot skip intermediate states."""
        assert not is_valid_transition("CHECKED_IN", "CLOSED", "admin")

    def test_closed_to_anything_not_allowed(self):
        """CLOSED is a terminal state with no outbound transitions."""
        assert not is_valid_transition("CLOSED", "PENDING", "admin")
        assert not is_valid_transition("CLOSED", "CHECKED_IN", "system")

    def test_cancelled_is_terminal(self):
        """CANCELLED has no outbound transitions."""
        assert not is_valid_transition("CANCELLED", "PENDING", "admin")
        assert not is_valid_transition("CANCELLED", "AUTO_CONFIRMED", "system")

    def test_unknown_status_pair(self):
        """Completely unknown statuses return False."""
        assert not is_valid_transition("IMAGINARY", "NOWHERE", "admin")

    def test_auto_confirmed_to_unloading_skips_steps(self):
        """Cannot jump from AUTO_CONFIRMED straight to UNLOADING."""
        assert not is_valid_transition("AUTO_CONFIRMED", "UNLOADING", "admin")


# ---------------------------------------------------------------------------
# Role restrictions
# ---------------------------------------------------------------------------


class TestRoleRestrictions:
    """Ensure certain roles cannot trigger certain transitions."""

    def test_warehouse_staff_cannot_reject(self):
        """warehouse_staff is not in the roles for PENDING->REJECTED."""
        assert not is_valid_transition("PENDING", "REJECTED", "warehouse_staff")

    def test_warehouse_staff_cannot_reject_confirmed(self):
        """warehouse_staff is not in the roles for AUTO_CONFIRMED->REJECTED."""
        assert not is_valid_transition("AUTO_CONFIRMED", "REJECTED", "warehouse_staff")

    def test_shipper_cannot_assign_dock(self):
        """Shipper role cannot move to DOCK_ASSIGNED."""
        assert not is_valid_transition("CHECKED_IN", "DOCK_ASSIGNED", "shipper")

    def test_carrier_cannot_start_unloading(self):
        """Carrier role cannot move to UNLOADING."""
        assert not is_valid_transition("DOCK_ASSIGNED", "UNLOADING", "carrier")

    def test_driver_cannot_close(self):
        """Driver cannot close an appointment."""
        assert not is_valid_transition("PICKED_UP", "CLOSED", "driver")

    def test_shipper_cannot_mark_no_show(self):
        """Only system can mark no-show."""
        assert not is_valid_transition("AUTO_CONFIRMED", "NO_SHOW", "shipper")
        assert not is_valid_transition("AUTO_CONFIRMED", "NO_SHOW", "admin")

    def test_driver_cannot_override_no_show(self):
        """Driver cannot override a no-show back to CHECKED_IN."""
        assert not is_valid_transition("NO_SHOW", "CHECKED_IN", "driver")


# ---------------------------------------------------------------------------
# Defect #6 fix: RESCHEDULED -> AUTO_CONFIRMED
# ---------------------------------------------------------------------------


class TestRescheduledTransition:
    """Verify RESCHEDULED is a transient state that can return to AUTO_CONFIRMED."""

    def test_rescheduled_to_auto_confirmed_by_system(self):
        assert is_valid_transition("RESCHEDULED", "AUTO_CONFIRMED", "system")

    def test_rescheduled_to_auto_confirmed_by_dispatcher(self):
        assert is_valid_transition("RESCHEDULED", "AUTO_CONFIRMED", "dispatcher")

    def test_rescheduled_to_auto_confirmed_by_admin(self):
        assert is_valid_transition("RESCHEDULED", "AUTO_CONFIRMED", "admin")

    def test_rescheduled_to_cancelled_by_shipper(self):
        """Shipper can cancel during reschedule."""
        assert is_valid_transition("RESCHEDULED", "CANCELLED", "shipper")

    def test_rescheduled_to_cancelled_by_carrier(self):
        assert is_valid_transition("RESCHEDULED", "CANCELLED", "carrier")

    def test_auto_confirmed_to_rescheduled_by_dispatcher(self):
        """Dispatcher can trigger reschedule."""
        assert is_valid_transition("AUTO_CONFIRMED", "RESCHEDULED", "dispatcher")

    def test_rescheduled_transition_has_notify_action(self):
        """The RESCHEDULED->AUTO_CONFIRMED transition fires notify_confirmed."""
        rule = get_transition("RESCHEDULED", "AUTO_CONFIRMED")
        assert rule is not None
        assert "notify_confirmed" in rule["actions"]


# ---------------------------------------------------------------------------
# get_allowed_transitions
# ---------------------------------------------------------------------------


class TestGetAllowedTransitions:
    """Verify get_allowed_transitions returns the correct set for each state/role."""

    def test_pending_admin_transitions(self):
        allowed = get_allowed_transitions("PENDING", "admin")
        assert "AUTO_CONFIRMED" in allowed
        assert "REJECTED" in allowed
        assert "CANCELLED" in allowed
        # Should not include transitions that require system-only
        assert "UNLOADING" not in allowed

    def test_pending_shipper_transitions(self):
        allowed = get_allowed_transitions("PENDING", "shipper")
        assert "CANCELLED" in allowed
        # Shipper can access system transitions via the fallback
        assert "AUTO_CONFIRMED" in allowed  # system is in roles, so shipper gets it too

    def test_checked_in_dispatcher_transitions(self):
        allowed = get_allowed_transitions("CHECKED_IN", "dispatcher")
        assert "DOCK_ASSIGNED" in allowed
        assert "EXCEPTION_AT_GATE" in allowed

    def test_closed_has_no_transitions(self):
        """Terminal state has no outbound transitions for any role."""
        assert get_allowed_transitions("CLOSED", "admin") == []
        assert get_allowed_transitions("CLOSED", "system") == []

    def test_all_defined_transitions_are_reachable(self):
        """Every entry in TRANSITIONS should be reachable by at least one listed role."""
        for (from_s, to_s), rule in TRANSITIONS.items():
            reachable = False
            for role in rule["roles"]:
                if is_valid_transition(from_s, to_s, role):
                    reachable = True
                    break
            assert reachable, f"Transition ({from_s} -> {to_s}) not reachable by any listed role"

    def test_transition_has_actions_key(self):
        """Every transition definition must have an 'actions' list."""
        for key, rule in TRANSITIONS.items():
            assert "actions" in rule, f"Transition {key} missing 'actions'"
            assert isinstance(rule["actions"], list), f"Transition {key} 'actions' is not a list"

    def test_transition_has_roles_key(self):
        """Every transition definition must have a 'roles' list."""
        for key, rule in TRANSITIONS.items():
            assert "roles" in rule, f"Transition {key} missing 'roles'"
            assert len(rule["roles"]) > 0, f"Transition {key} has empty 'roles'"
