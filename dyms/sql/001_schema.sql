-- ============================================
-- DYMS V2.2 Complete Database Schema
-- PostgreSQL 15+
-- ============================================

-- 1. Facilities
CREATE TABLE facilities (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(20) UNIQUE NOT NULL,
    name            VARCHAR(100) NOT NULL,
    address         TEXT,
    timezone        VARCHAR(50) DEFAULT 'America/New_York',
    operating_hours JSONB DEFAULT '{"start":"08:00","end":"17:00"}',
    holidays_json   JSONB DEFAULT '[]',
    geo_lat         DECIMAL(10,7),
    geo_lng         DECIMAL(10,7),
    geo_radius_m    INTEGER DEFAULT 500,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Facility Locations (Dock + Yard)
CREATE TABLE facility_locations (
    id                  SERIAL PRIMARY KEY,
    facility_id         INTEGER NOT NULL REFERENCES facilities(id),
    location_type       VARCHAR(10) NOT NULL CHECK (location_type IN ('DOCK','YARD')),
    code                VARCHAR(20) NOT NULL,
    status              VARCHAR(20) DEFAULT 'AVAILABLE'
                        CHECK (status IN ('AVAILABLE','OCCUPIED','MAINTENANCE')),
    has_leveler         BOOLEAN DEFAULT TRUE,
    max_weight_lbs      INTEGER,
    accepts_sizes_json  JSONB DEFAULT '["20ft","40ft","45ft","53ft"]',
    sort_order          INTEGER DEFAULT 0,
    is_active           BOOLEAN DEFAULT TRUE,
    UNIQUE (facility_id, code)
);

-- 3. Users
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    display_name    VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL
                    CHECK (role IN ('admin','dispatcher','warehouse_staff','shipper','carrier','driver')),
    email           VARCHAR(255),
    phone           VARCHAR(30),
    company_name    VARCHAR(200),
    dmv_number      VARCHAR(50),
    facility_ids    JSONB DEFAULT '[1]',
    is_active       BOOLEAN DEFAULT TRUE,
    must_change_pwd BOOLEAN DEFAULT TRUE,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 4. ASN (Advance Shipping Notice)
CREATE TABLE asns (
    id                  SERIAL PRIMARY KEY,
    facility_id         INTEGER NOT NULL REFERENCES facilities(id),
    shipper_id          INTEGER NOT NULL REFERENCES users(id),
    container_number    VARCHAR(30),
    cargo_type          VARCHAR(20) NOT NULL CHECK (cargo_type IN ('PALLETIZED','FLOOR_LOAD')),
    expected_qty        INTEGER,
    qty_unit            VARCHAR(10) DEFAULT 'BOXES' CHECK (qty_unit IN ('BOXES','PALLETS')),
    reference_number    VARCHAR(100),
    packing_list_path   TEXT,
    truck_plate         VARCHAR(30),
    truck_company       VARCHAR(200),
    truck_dmv           VARCHAR(50),
    notes               TEXT,
    status              VARCHAR(20) DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','CANCELLED')),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Appointments (Core)
CREATE TABLE appointments (
    id                      SERIAL PRIMARY KEY,
    facility_id             INTEGER NOT NULL REFERENCES facilities(id),
    asn_id                  INTEGER REFERENCES asns(id),
    shipper_id              INTEGER NOT NULL REFERENCES users(id),
    carrier_id              INTEGER REFERENCES users(id),

    -- Type
    appointment_type        VARCHAR(10) NOT NULL CHECK (appointment_type IN ('LIVE','DROP')),
    carrier_type            VARCHAR(10) NOT NULL DEFAULT 'own'
                            CHECK (carrier_type IN ('own','platform','self')),
    platform_name           VARCHAR(100),
    platform_order_id       VARCHAR(100),

    -- State Machine
    status                  VARCHAR(25) NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN (
                                'PENDING','AUTO_CONFIRMED','REJECTED','RESCHEDULED',
                                'CHECKED_IN','DOCK_ASSIGNED','UNLOADING',
                                'UNLOAD_COMPLETE','YARD_MOVED','AWAITING_PICKUP',
                                'PICKED_UP','CLOSED',
                                'EXCEPTION_AT_GATE','NO_SHOW','CANCELLED'
                            )),

    -- Schedule
    scheduled_start         TIMESTAMPTZ NOT NULL,
    scheduled_end           TIMESTAMPTZ NOT NULL,
    buffer_minutes          INTEGER DEFAULT 30,

    -- Actual Timestamps
    actual_arrival          TIMESTAMPTZ,
    actual_dock_start       TIMESTAMPTZ,
    actual_unload_start     TIMESTAMPTZ,
    actual_unload_complete  TIMESTAMPTZ,
    actual_pickup           TIMESTAMPTZ,
    actual_yard_move_at     TIMESTAMPTZ,

    -- Dock / Yard
    dock_id                 INTEGER REFERENCES facility_locations(id),
    yard_spot_id            INTEGER REFERENCES facility_locations(id),

    -- Driver Info
    driver_name             VARCHAR(100),
    driver_phone            VARCHAR(30),
    truck_plate             VARCHAR(30),
    checkin_token           VARCHAR(64) UNIQUE,

    -- GPS Check-in
    checkin_lat             DECIMAL(10,7),
    checkin_lng             DECIMAL(10,7),
    geo_flag                VARCHAR(15) DEFAULT 'OK'
                            CHECK (geo_flag IN ('OK','OUT_OF_RANGE','NO_GPS')),

    -- Safety Acknowledgement
    safety_ack_at           TIMESTAMPTZ,
    device_fingerprint      VARCHAR(255),

    -- Cargo Type Correction
    cargo_type_actual       VARCHAR(20),
    cargo_type_mismatch     BOOLEAN DEFAULT FALSE,

    -- BOL
    bol_number              VARCHAR(50),
    bol_file_path           TEXT,

    -- Billing Fields
    actual_unload_duration  INTEGER,
    yard_move_count         INTEGER DEFAULT 0,
    reschedule_count        INTEGER DEFAULT 0,

    -- LTL (Phase 2)
    ltl_master_pro          VARCHAR(50),

    -- Audit
    created_by              INTEGER REFERENCES users(id),
    confirmed_by            INTEGER REFERENCES users(id),
    cancelled_by            INTEGER REFERENCES users(id),
    cancel_reason           TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Concurrency indexes
CREATE INDEX idx_appt_dock_schedule ON appointments(dock_id, scheduled_start, scheduled_end)
    WHERE status NOT IN ('CANCELLED','REJECTED','NO_SHOW','CLOSED');
CREATE INDEX idx_appt_facility_status ON appointments(facility_id, status);
CREATE INDEX idx_appt_shipper ON appointments(shipper_id);
CREATE INDEX idx_appt_checkin_token ON appointments(checkin_token) WHERE checkin_token IS NOT NULL;

-- 6. Appointment-ASN Many-to-Many (LTL)
CREATE TABLE appointment_asns (
    id              SERIAL PRIMARY KEY,
    appointment_id  INTEGER NOT NULL REFERENCES appointments(id),
    asn_id          INTEGER NOT NULL REFERENCES asns(id),
    is_arrived      BOOLEAN DEFAULT FALSE,
    UNIQUE (appointment_id, asn_id)
);

-- 7. Evidence
CREATE TABLE appointment_evidence (
    id              SERIAL PRIMARY KEY,
    appointment_id  INTEGER NOT NULL REFERENCES appointments(id),
    photo_type      VARCHAR(25) NOT NULL
                    CHECK (photo_type IN ('TRUCK_REAR','SEAL_PHOTO','DOOR_OPEN','CLEAR_OUT','EXCEPTION','YARD_WALK')),
    file_path       TEXT NOT NULL,
    thumbnail_path  TEXT,
    cloud_path      TEXT,
    sync_status     VARCHAR(10) DEFAULT 'SYNCED'
                    CHECK (sync_status IN ('LOCAL','UPLOADING','SYNCED','FAILED')),
    gps_lat         DECIMAL(10,7),
    gps_lng         DECIMAL(10,7),
    taken_at        TIMESTAMPTZ DEFAULT NOW(),
    taken_by        INTEGER REFERENCES users(id),
    notes           TEXT,
    litigation_hold BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_evidence_appt ON appointment_evidence(appointment_id);
CREATE INDEX idx_evidence_sync ON appointment_evidence(sync_status) WHERE sync_status != 'SYNCED';

-- 8. Billing Events
CREATE TABLE billing_events (
    id              SERIAL PRIMARY KEY,
    facility_id     INTEGER NOT NULL REFERENCES facilities(id),
    appointment_id  INTEGER NOT NULL REFERENCES appointments(id),
    shipper_id      INTEGER NOT NULL REFERENCES users(id),
    event_type      VARCHAR(20) NOT NULL
                    CHECK (event_type IN ('DETENTION','NO_SHOW','OVERTIME','SHUNTING')),
    amount          DECIMAL(10,2) NOT NULL,
    currency        VARCHAR(3) DEFAULT 'USD',
    status          VARCHAR(15) DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING','INVOICED','WAIVED','PAID')),
    free_period_end TIMESTAMPTZ,
    billable_start  TIMESTAMPTZ,
    billable_end    TIMESTAMPTZ,
    waived_by       INTEGER REFERENCES users(id),
    waive_reason    TEXT,
    liable_party    VARCHAR(20) DEFAULT 'shipper'
                    CHECK (liable_party IN ('shipper','carrier','warehouse')),
    liable_note     TEXT,
    rate_snapshot   JSONB,
    invoice_id      INTEGER REFERENCES invoices(id),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_billing_shipper ON billing_events(shipper_id, status);

-- 9. Invoices
CREATE TABLE invoices (
    id              SERIAL PRIMARY KEY,
    facility_id     INTEGER NOT NULL REFERENCES facilities(id),
    shipper_id      INTEGER NOT NULL REFERENCES users(id),
    invoice_number  VARCHAR(30) UNIQUE NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    total_amount    DECIMAL(10,2) NOT NULL,
    status          VARCHAR(15) DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT','SENT','PAID','OVERDUE')),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 10. Billing Config
CREATE TABLE billing_config (
    id              SERIAL PRIMARY KEY,
    facility_id     INTEGER NOT NULL REFERENCES facilities(id),
    config_key      VARCHAR(50) NOT NULL,
    config_value    JSONB NOT NULL,
    UNIQUE (facility_id, config_key)
);

-- 11. Audit Log
CREATE TABLE audit_log (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id),
    user_display    VARCHAR(100),
    action          VARCHAR(50) NOT NULL,
    target          VARCHAR(200),
    payload         JSONB,
    ip_address      VARCHAR(45),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_time ON audit_log(created_at DESC);

-- 12. Settings
CREATE TABLE settings (
    key             VARCHAR(100) PRIMARY KEY,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
