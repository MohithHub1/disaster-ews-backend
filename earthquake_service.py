import requests
from datetime import datetime, timedelta, timezone


USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def get_earthquake_activity(
    latitude: float,
    longitude: float,
    radius_km: float = 200.0,
    days: int = 30,
):
    """
    Fetch recent earthquakes near the selected location
    using the official USGS earthquake API.
    """

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    params = {
        "format": "geojson",
        "starttime": start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "latitude": latitude,
        "longitude": longitude,
        "maxradiuskm": radius_km,
        "orderby": "time",
        "limit": 100,
    }

    response = requests.get(
        USGS_URL,
        params=params,
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    earthquakes = []

    for feature in data.get("features", []):
        properties = feature.get("properties", {})

        magnitude = properties.get("mag")
        place = properties.get("place")
        event_time = properties.get("time")

        if magnitude is None:
            continue

        earthquakes.append({
            "magnitude": float(magnitude),
            "place": place,
            "time": event_time,
        })

    max_magnitude = max(
        (earthquake["magnitude"] for earthquake in earthquakes),
        default=0.0,
    )

    return {
        "earthquake_count": len(earthquakes),
        "max_magnitude": max_magnitude,
        "earthquakes": earthquakes,
    }