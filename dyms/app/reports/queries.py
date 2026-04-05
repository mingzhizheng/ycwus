"""PostgreSQL queries for reporting views."""

DOCK_UTILIZATION_QUERY = """
    SELECT
        fl.code as dock_code,
        COUNT(a.id) as total_appointments,
        COUNT(CASE WHEN a.status = 'CLOSED' THEN 1 END) as completed,
        COUNT(CASE WHEN a.status = 'NO_SHOW' THEN 1 END) as no_shows,
        COUNT(CASE WHEN a.status = 'CANCELLED' THEN 1 END) as cancelled,
        AVG(a.actual_unload_duration) as avg_unload_minutes,
        COUNT(CASE WHEN a.cargo_type_mismatch THEN 1 END) as type_mismatches
    FROM facility_locations fl
    LEFT JOIN appointments a ON a.dock_id = fl.id
        AND DATE(a.scheduled_start) BETWEEN :start_date AND :end_date
    WHERE fl.facility_id = :facility_id AND fl.location_type = 'DOCK'
    GROUP BY fl.code
    ORDER BY fl.code
"""

SHIPPER_RANKING_QUERY = """
    SELECT
        u.display_name as shipper_name,
        u.company_name,
        COUNT(a.id) as total_appointments,
        COUNT(CASE WHEN a.status = 'NO_SHOW' THEN 1 END) as no_shows,
        COUNT(CASE WHEN a.cargo_type_mismatch THEN 1 END) as type_mismatches,
        COALESCE(SUM(b.amount), 0) as total_charges
    FROM users u
    LEFT JOIN appointments a ON a.shipper_id = u.id
        AND DATE(a.scheduled_start) BETWEEN :start_date AND :end_date
    LEFT JOIN billing_events b ON b.shipper_id = u.id
        AND b.created_at BETWEEN :start_date AND :end_date
    WHERE u.role = 'shipper'
    GROUP BY u.id, u.display_name, u.company_name
    ORDER BY total_appointments DESC
"""

DAILY_SUMMARY_QUERY = """
    SELECT
        DATE(a.scheduled_start) as date,
        COUNT(*) as total,
        COUNT(CASE WHEN a.status = 'CLOSED' THEN 1 END) as completed,
        COUNT(CASE WHEN a.status = 'NO_SHOW' THEN 1 END) as no_shows,
        COUNT(CASE WHEN a.appointment_type = 'LIVE' THEN 1 END) as live_count,
        COUNT(CASE WHEN a.appointment_type = 'DROP' THEN 1 END) as drop_count
    FROM appointments a
    WHERE a.facility_id = :facility_id
      AND DATE(a.scheduled_start) BETWEEN :start_date AND :end_date
    GROUP BY DATE(a.scheduled_start)
    ORDER BY date
"""
