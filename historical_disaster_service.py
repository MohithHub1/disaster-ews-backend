import math
from datetime import datetime, timedelta, timezone

import requests


GDACS_URL = (
    "https://www.gdacs.org/gdacsapi/api/"
    "Events/geteventlist/SEARCH"
)

SEARCH_YEARS = 5
MAX_DISTANCE_KM = 100.0
REQUEST_TIMEOUT = 10


def _distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * radius * math.asin(
        math.sqrt(a)
    )


def _get_coordinates(feature):
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")

    if (
        geometry.get("type") == "Point"
        and isinstance(coordinates, list)
        and len(coordinates) >= 2
    ):
        return (
            float(coordinates[1]),
            float(coordinates[0]),
        )

    return None


def get_historical_disaster_risk(
    latitude: float,
    longitude: float,
):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(
        days=365 * SEARCH_YEARS
    )

    events = []

    params = {
        "eventlist": "EQ;FL",
        "fromdate": start_date.strftime(
            "%Y-%m-%d"
        ),
        "todate": end_date.strftime(
            "%Y-%m-%d"
        ),
        "alertlevel": "red;orange;green",
        "pagesize": 100,
        "pagenumber": 1,
    }

    try:
        response = requests.get(
            GDACS_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

    except Exception as e:
        print(
            f"HISTORICAL DISASTER API ERROR: {e}"
        )

        return {
            "historical_risk": 0.0,
            "event_count": 0,
            "search_years": SEARCH_YEARS,
            "radius_km": MAX_DISTANCE_KM,
            "events": [],
            "source": "GDACS",
            "available": False,
        }

    features = data.get("features", [])

    for feature in features:
        coordinates = _get_coordinates(feature)

        if coordinates is None:
            continue

        event_latitude, event_longitude = coordinates

        distance = _distance_km(
            latitude,
            longitude,
            event_latitude,
            event_longitude,
        )

        if distance > MAX_DISTANCE_KM:
            continue

        properties = (
            feature.get("properties") or {}
        )

        events.append(
            {
                "type": properties.get(
                    "eventtype"
                ),
                "distance_km": round(
                    distance,
                    2,
                ),
                "description": properties.get(
                    "description"
                ),
                "country": properties.get(
                    "country"
                ),
                "date": properties.get(
                    "todate"
                ),
            }
        )

    event_count = len(events)

    if event_count == 0:
        risk_score = 0.0
    elif event_count == 1:
        risk_score = 20.0
    elif event_count == 2:
        risk_score = 40.0
    elif event_count == 3:
        risk_score = 60.0
    elif event_count == 4:
        risk_score = 80.0
    else:
        risk_score = 100.0

    return {
        "historical_risk": risk_score,
        "event_count": event_count,
        "search_years": SEARCH_YEARS,
        "radius_km": MAX_DISTANCE_KM,
        "events": events,
        "source": "GDACS",
        "available": True,
    }