-- Initial Facility
INSERT INTO facilities (code, name, address, timezone, geo_lat, geo_lng) VALUES
('WH-ATL-01', 'Atlanta Main Warehouse', '1234 Logistics Blvd, Duluth, GA 30096',
 'America/New_York', 34.0028, -84.1455);

-- 10 Dock Doors
INSERT INTO facility_locations (facility_id, location_type, code, sort_order)
SELECT 1, 'DOCK', 'D-' || LPAD(n::TEXT, 2, '0'), n
FROM generate_series(1, 10) AS n;

-- 10 Yard Spots
INSERT INTO facility_locations (facility_id, location_type, code, sort_order)
SELECT 1, 'YARD', 'Y-' || LPAD(n::TEXT, 2, '0'), n
FROM generate_series(1, 10) AS n;

-- Admin User (password: admin123)
-- bcrypt hash of 'admin123'
INSERT INTO users (username, password_hash, display_name, role, email, must_change_pwd)
VALUES ('admin', '$2b$12$LJ3m4ks7he/GQqF3B.kzOey1E4NzGHD3F8H1Ut9fHxZCjkb1vGzXy',
        'System Admin', 'admin', 'admin@dyms.local', true);

-- Billing Config
INSERT INTO billing_config (facility_id, config_key, config_value) VALUES
(1, 'detention_free_hours', '48'),
(1, 'detention_tiers', '[{"from_day":1,"to_day":3,"rate_per_day":50},{"from_day":4,"to_day":null,"rate_per_day":100}]'),
(1, 'noshow_amount', '50'),
(1, 'overtime_enabled', 'false'),
(1, 'shunting_enabled', 'false'),
(1, 'working_days_only', 'false'),
(1, 'late_tolerance_minutes', '30'),
(1, 'drop_auto_schedule_hours', '24');

-- Safety Notice (EN/ZH)
INSERT INTO settings (key, value) VALUES
('safety_notice', '{
  "en": "SAFETY NOTICE: All visitors must wear PPE (hard hat, safety vest, steel-toe boots) at all times in the dock area. No smoking. Stay within designated walkways. Report any unsafe conditions immediately.",
  "zh": "安全告知：所有进入月台区域的人员必须全程穿戴 PPE（安全帽、反光背心、钢头靴）。禁止吸烟。请在指定通道内行走。发现不安全情况请立即报告。"
}');

-- Cargo Duration Settings
INSERT INTO settings (key, value) VALUES
('cargo_duration_minutes', '{"PALLETIZED":60,"FLOOR_LOAD":180}');
