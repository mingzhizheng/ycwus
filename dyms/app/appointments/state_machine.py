"""
Appointment State Machine — Transition Matrix

Each key is (from_status, to_status).
Value contains:
  - roles: who can trigger
  - preconditions: list of check names
  - actions: list of action names to execute
"""

TRANSITIONS = {
    # === PENDING ===
    ("PENDING", "AUTO_CONFIRMED"): {
        "roles": ["system", "admin", "dispatcher"],
        "actions": ["lock_slot", "generate_token", "notify_confirmed"],
    },
    ("PENDING", "REJECTED"): {
        "roles": ["dispatcher", "admin"],
        "actions": ["notify_rejected", "release_slot"],
    },
    ("PENDING", "CANCELLED"): {
        "roles": ["shipper", "carrier", "admin"],
        "actions": ["check_noshow_penalty", "release_slot"],
    },

    # === AUTO_CONFIRMED ===
    ("AUTO_CONFIRMED", "CHECKED_IN"): {
        "roles": ["driver", "warehouse_staff", "dispatcher", "admin"],
        "preconditions": ["valid_token", "safety_acknowledged"],
        "actions": ["record_arrival", "compute_geo_flag"],
    },
    ("AUTO_CONFIRMED", "REJECTED"): {
        "roles": ["dispatcher", "admin"],
        "actions": ["notify_rejected", "release_slot"],
    },
    ("AUTO_CONFIRMED", "RESCHEDULED"): {
        "roles": ["dispatcher", "admin"],
        "actions": ["release_slot", "lock_new_slot", "increment_reschedule"],
    },
    # RESCHEDULED is transient — once new slot is confirmed, goes back to AUTO_CONFIRMED
    ("RESCHEDULED", "AUTO_CONFIRMED"): {
        "roles": ["system", "dispatcher", "admin"],
        "actions": ["notify_confirmed"],
    },
    ("RESCHEDULED", "CANCELLED"): {
        "roles": ["shipper", "carrier", "admin"],
        "actions": ["check_noshow_penalty", "release_slot"],
    },
    ("AUTO_CONFIRMED", "CANCELLED"): {
        "roles": ["shipper", "carrier", "admin"],
        "actions": ["check_noshow_penalty", "release_slot"],
    },
    ("AUTO_CONFIRMED", "NO_SHOW"): {
        "roles": ["system"],
        "preconditions": ["past_tolerance_window"],
        "actions": ["create_noshow_charge", "notify_noshow", "release_slot"],
    },

    # === CHECKED_IN ===
    ("CHECKED_IN", "EXCEPTION_AT_GATE"): {
        "roles": ["driver", "warehouse_staff", "dispatcher"],
        "preconditions": ["exception_photos_uploaded"],
        "actions": ["block_receipt", "notify_exception"],
    },
    ("CHECKED_IN", "DOCK_ASSIGNED"): {
        "roles": ["dispatcher", "admin"],
        "preconditions": ["dock_available"],
        "actions": ["occupy_dock", "notify_driver_dock"],
    },

    # === DOCK_ASSIGNED ===
    ("DOCK_ASSIGNED", "UNLOADING"): {
        "roles": ["warehouse_staff", "dispatcher", "admin"],
        "actions": ["record_unload_start"],
    },

    # === UNLOADING ===
    ("UNLOADING", "UNLOAD_COMPLETE"): {
        "roles": ["warehouse_staff", "dispatcher", "admin"],
        "preconditions": ["clear_out_photo_uploaded"],
        "actions": ["record_unload_complete", "start_detention_timer"],
    },

    # === UNLOAD_COMPLETE ===
    ("UNLOAD_COMPLETE", "YARD_MOVED"): {
        "roles": ["warehouse_staff", "dispatcher", "admin"],
        "actions": ["release_dock", "increment_yard_move", "create_shunting_charge"],
    },
    ("UNLOAD_COMPLETE", "AWAITING_PICKUP"): {
        "roles": ["system", "dispatcher", "admin"],
        "actions": ["release_dock"],
    },

    # === YARD_MOVED ===
    ("YARD_MOVED", "AWAITING_PICKUP"): {
        "roles": ["system", "dispatcher", "admin"],
        "actions": [],
    },

    # === AWAITING_PICKUP ===
    ("AWAITING_PICKUP", "PICKED_UP"): {
        "roles": ["warehouse_staff", "dispatcher", "admin"],
        "actions": ["record_pickup"],
    },

    # === PICKED_UP ===
    ("PICKED_UP", "CLOSED"): {
        "roles": ["system", "admin"],
        "actions": ["finalize"],
    },

    # === Overrides ===
    ("NO_SHOW", "CHECKED_IN"): {
        "roles": ["dispatcher", "admin"],
        "actions": ["revoke_noshow_charge", "record_arrival"],
    },
    ("EXCEPTION_AT_GATE", "CHECKED_IN"): {
        "roles": ["dispatcher", "admin"],
        "actions": ["clear_exception"],
    },
}


def get_transition(from_status: str, to_status: str) -> dict | None:
    return TRANSITIONS.get((from_status, to_status))


def is_valid_transition(from_status: str, to_status: str, role: str) -> bool:
    rule = get_transition(from_status, to_status)
    if not rule:
        return False
    return role in rule["roles"] or "system" in rule["roles"]


def get_allowed_transitions(from_status: str, role: str) -> list[str]:
    results = []
    for (f, t), rule in TRANSITIONS.items():
        if f == from_status and (role in rule["roles"] or "system" in rule["roles"]):
            results.append(t)
    return results
