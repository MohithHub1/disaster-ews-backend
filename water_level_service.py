from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2
from typing import Optional


MAX_STATION_DISTANCE_KM = 50.0

# A water-level observation older than this is not treated as current.
MAX_OBSERVATION_AGE_HOURS = 6.0


def _distance_km(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    """Calculate the great-circle distance between two coordinates."""

    earth_radius_km = 6371.0

    lat1 = radians(latitude1)
    lat2 = radians(latitude2)

    delta_lat = radians(latitude2 - latitude1)
    delta_lon = radians(longitude2 - longitude1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius_km * c


def _is_recent(observed_at: str) -> bool:
    """Return True only when the observation is recent enough."""

    try:
        timestamp = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        age_hours = (
            datetime.now(timezone.utc) - timestamp
        ).total_seconds() / 3600.0

        return (
            age_hours >= 0
            and age_hours <= MAX_OBSERVATION_AGE_HOURS
        )

    except (TypeError, ValueError):
        return False


def find_nearest_station(
    latitude: float,
    longitude: float,
    stations: list[dict],
) -> Optional[dict]:
    """Find the nearest recent and geographically suitable station."""

    nearest_station = None
    nearest_distance = None

    for station in stations:
        try:
            if not _is_recent(station.get("observed_at")):
                continue

            station_latitude = float(
                station["latitude"]
            )
            station_longitude = float(
                station["longitude"]
            )

            distance = _distance_km(
                latitude,
                longitude,
                station_latitude,
                station_longitude,
            )

            if distance > MAX_STATION_DISTANCE_KM:
                continue

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest_distance = distance
                nearest_station = station

        except (KeyError, TypeError, ValueError):
            continue

    if nearest_station is None:
        return None

    return {
        **nearest_station,
        "distance_km": round(
            nearest_distance,
            2,
        ),
    }


def get_water_level(
    latitude: float,
    longitude: float,
    stations: list[dict],
) -> dict:
    """
    Return the nearest suitable and recent water-level station.

    Distinguishes between:
    - no station within the allowed distance
    - station exists but its observation is stale
    """

    nearest_station = None
    nearest_distance = None

    for station in stations:
        try:
            station_latitude = float(
                station["latitude"]
            )
            station_longitude = float(
                station["longitude"]
            )

            distance = _distance_km(
                latitude,
                longitude,
                station_latitude,
                station_longitude,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                nearest_distance = distance
                nearest_station = station

        except (KeyError, TypeError, ValueError):
            continue

    if nearest_station is None:
        return {
            "available": False,
            "reason": "No water-level station found.",
        }

    if nearest_distance > MAX_STATION_DISTANCE_KM:
        return {
            "available": False,
            "reason": (
                "No suitable water-level station "
                "within 50 km."
            ),
            "nearest_station": nearest_station.get(
                "station_name"
            ),
            "nearest_distance_km": round(
                nearest_distance,
                2,
            ),
        }

    if not _is_recent(
        nearest_station.get("observed_at")
    ):
        return {
            "available": False,
            "reason": (
                "Nearest station exists, but its "
                "water-level observation is older "
                "than 6 hours."
            ),
            "nearest_station": nearest_station.get(
                "station_name"
            ),
            "distance_km": round(
                nearest_distance,
                2,
            ),
            "last_observed_at": nearest_station.get(
                "observed_at"
            ),
        }

    return {
        "available": True,
        "water_level_m": nearest_station.get(
            "water_level_m"
        ),
        "station_name": nearest_station.get(
            "station_name"
        ),
        "river": nearest_station.get("river"),
        "state": nearest_station.get("state"),
        "district": nearest_station.get(
            "district"
        ),
        "village": nearest_station.get(
            "village"
        ),
        "distance_km": round(
            nearest_distance,
            2,
        ),
        "observed_at": nearest_station.get(
            "observed_at"
        ),
    }