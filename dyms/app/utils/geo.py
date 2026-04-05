from math import radians, sin, cos, sqrt, atan2


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the distance in meters between two points on Earth."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def compute_geo_flag(
    checkin_lat: float | None,
    checkin_lng: float | None,
    facility_lat: float,
    facility_lng: float,
    radius_m: int = 500,
) -> str:
    if checkin_lat is None or checkin_lng is None:
        return "NO_GPS"
    dist = haversine_meters(checkin_lat, checkin_lng, facility_lat, facility_lng)
    return "OK" if dist <= radius_m else "OUT_OF_RANGE"
