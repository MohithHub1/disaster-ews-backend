import math
import requests


OVERPASS_URL = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"


def _distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate great-circle distance between two coordinates."""

    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c


def get_water_proximity(
    latitude: float,
    longitude: float,
    radius_km: float = 10.0,
):
    """
    Find the nearest mapped water feature using OpenStreetMap.

    Searches for:
    - rivers
    - streams
    - canals
    - lakes
    - reservoirs
    """

    radius_m = int(radius_km * 1000)

    
    query = f"""
    [out:json][timeout:60];

    (
      way["waterway"~"river|stream|canal"](
        around:{radius_m},{latitude},{longitude}
      );

      way["natural"="water"](
        around:{radius_m},{latitude},{longitude}
      );

      node["natural"="water"](
        around:{radius_m},{latitude},{longitude}
      );
    );

    out center;
    """
    response = requests.post(
        OVERPASS_URL,
        data=query,
        headers={
            "User-Agent": "DisasterEWS/1.0 (educational project)",
            "Accept": "application/json",
            "Content-Type": "text/plain",
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    nearest_distance = None
    nearest_feature = None

    for element in data.get("elements", []):
        element_type = element.get("type")

        points = []

        if element_type == "node":
            element_lat = element.get("lat")
            element_lon = element.get("lon")

            if (
                element_lat is not None
                and element_lon is not None
            ):
                points.append(
                    (
                        float(element_lat),
                        float(element_lon),
                    )
                )

        elif element_type == "way":
            geometry = element.get("geometry", [])

            for point in geometry:
                point_lat = point.get("lat")
                point_lon = point.get("lon")

                if (
                    point_lat is not None
                    and point_lon is not None
                ):
                    points.append(
                        (
                            float(point_lat),
                            float(point_lon),
                        )
                    )

        if not points:
            center = element.get("center")

            if center:
                center_lat = center.get("lat")
                center_lon = center.get("lon")

                if (
                    center_lat is not None
                    and center_lon is not None
                ):
                    points.append(
                        (
                            float(center_lat),
                            float(center_lon),
                        )
                    )

        for point_lat, point_lon in points:
            distance = _distance_km(
                latitude,
                longitude,
                point_lat,
                point_lon,
            )

            if (
                nearest_distance is None
                or distance < nearest_distance
            ):
                tags = element.get("tags", {})

                nearest_distance = distance

                nearest_feature = {
                    "name": tags.get(
                        "name",
                        "Unnamed water feature",
                    ),
                    "water_type": (
                        tags.get("waterway")
                        or tags.get("natural")
                        or "water"
                    ),
                    "latitude": point_lat,
                    "longitude": point_lon,
                    "osm_id": element.get("id"),
                }

    if nearest_distance is None:
        return {
            "available": False,
            "distance_km": None,
            "feature": None,
        }

    return {
        "available": True,
        "distance_km": round(nearest_distance, 3),
        "feature": nearest_feature,
    }