import json
import urllib.parse
import urllib.request
import http.client
import socket
import ssl

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import Base, engine, SessionLocal
from models import Assessment
from schemas import AssessmentCreate


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# ADD NEW ASSESSMENT COLUMNS TO EXISTING DATABASES
# ============================================================

with engine.connect() as conn:
    columns = {
        "risk_level": "VARCHAR",
        "overall_risk": "FLOAT",
        "flood_risk": "FLOAT",
        "landslide_risk": "FLOAT",
        "lead_time_minutes": "INTEGER",
        "recommended_action": "VARCHAR",
    }

    for column, column_type in columns.items():
        try:
            conn.execute(
                text(
                    f"ALTER TABLE assessments "
                    f"ADD COLUMN {column} {column_type}"
                )
            )
            conn.commit()
        except Exception:
            pass


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Disaster Early Warning System"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE SESSION
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Disaster EWS backend is running"
    }


# ============================================================
# CREATE ASSESSMENT
# ============================================================

@app.post("/assessments")
def create_assessment(
    assessment: AssessmentCreate,
    db: Session = Depends(get_db),
):
    new_assessment = Assessment(
        location=assessment.location,
        rainfall=assessment.rainfall,
        risk_level=assessment.risk_level,
        overall_risk=assessment.overall_risk,
        flood_risk=assessment.flood_risk,
        landslide_risk=assessment.landslide_risk,
        lead_time_minutes=assessment.lead_time_minutes,
        recommended_action=assessment.recommended_action,
        soil_moisture=assessment.soil_moisture,
        water_level=assessment.water_level,
        temperature=assessment.temperature,
        humidity=assessment.humidity,
        wind_speed=assessment.wind_speed,
        slope=assessment.slope,
        historical_disaster=assessment.historical_disaster,
    )

    db.add(new_assessment)
    db.commit()
    db.refresh(new_assessment)

    return {
        "message": "Assessment stored successfully",
        "id": new_assessment.id,
    }

def _overpass_post_ipv4(
    url: str,
    encoded_query: bytes,
):
    parsed = urllib.parse.urlparse(url)

    host = parsed.hostname
    port = parsed.port or 443

    if host is None:
        raise ValueError("Invalid Overpass URL")

    addresses = socket.getaddrinfo(
        host,
        port,
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    if not addresses:
        raise OSError(
            f"No IPv4 address found for {host}"
        )

    ipv4_address = addresses[0][4][0]

    context = ssl.create_default_context()

    raw_socket = socket.create_connection(
        (ipv4_address, port),
        timeout=30,
    )

    ssl_socket = context.wrap_socket(
        raw_socket,
        server_hostname=host,
    )

    connection = http.client.HTTPSConnection(
        host,
        port,
        timeout=30,
    )

    connection.sock = ssl_socket

    try:
        connection.request(
            "POST",
            parsed.path or "/api/interpreter",
            body=encoded_query,
            headers={
                "User-Agent": "DisasterEWS/1.0",
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                ),
            },
        )

        response = connection.getresponse()
        response_body = response.read()

        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"Overpass HTTP {response.status}: "
                f"{response_body[:500].decode('utf-8', errors='replace')}"
            )

        return json.loads(
            response_body.decode("utf-8")
        )

    finally:
        connection.close()
# ============================================================
# GET ASSESSMENTS
# ============================================================

@app.get("/shelters")
def get_shelters(
    lat: float,
    lon: float,
    radius: int = 50000,
):
    """
    Find emergency shelters / evacuation points near a location.

    Sources:
    - OSM designated shelters
    - OSM emergency assembly points
    - OSM disaster help points
    - OSM evacuation centres

    Designed for India-wide operation.
    """

    query = f"""
    [out:json][timeout:60];

    (
      /*
       * Official/designated emergency shelters
       */
      nwr[
        "emergency:social_facility"="shelter"
      ](around:{radius},{lat},{lon});

      nwr[
        "social_facility"="shelter"
      ](around:{radius},{lat},{lon});

      nwr[
        "emergency:shelter"="yes"
      ](around:{radius},{lat},{lon});

      nwr[
        "evacuation_center"="yes"
      ](around:{radius},{lat},{lon});

      /*
       * Emergency assembly locations
       */
      nwr[
        "emergency"="assembly_point"
      ](around:{radius},{lat},{lon});

      /*
       * Disaster help points
       */
      nwr[
        "emergency"="disaster_help_point"
      ](around:{radius},{lat},{lon});

      /*
       * General mapped shelters
       *
       * Public transport shelters are excluded.
       */
      nwr[
        "amenity"="shelter"
      ](
        around:{radius},{lat},{lon}
      )["shelter_type"!="public_transport"];
    );

    out center tags;
    """

    encoded_query = urllib.parse.urlencode(
        {"data": query}
    ).encode("utf-8")

    urls = [
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
    ]

    last_error = None
    data = None

    for url in urls:
        try:
            data = _overpass_post_ipv4(
                url,
                encoded_query,
            )
            break
        except Exception as e:
            last_error = str(e)

    if data is None:
        return {
            "success": False,
            "error": last_error or "All shelter providers failed",
            "shelters": [],
        }

    shelters = []
    seen_ids = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        element_id = (
            f"{element.get('type')}_{element.get('id')}"
        )

        if element_id in seen_ids:
            continue

        seen_ids.add(element_id)

        latitude = element.get("lat")
        longitude = element.get("lon")

        if latitude is None or longitude is None:
            center = element.get("center", {})

            latitude = center.get("lat")
            longitude = center.get("lon")

        if latitude is None or longitude is None:
            continue

        # -----------------------------------------
        # Determine emergency classification
        # -----------------------------------------

        if (
            tags.get("emergency:social_facility")
            == "shelter"
            or tags.get("social_facility")
            == "shelter"
            or tags.get("emergency:shelter")
            == "yes"
            or tags.get("evacuation_center")
            == "yes"
        ):
            shelter_type = "Emergency Shelter"
            verification = "OSM_EMERGENCY_SHELTER"
            priority = 1

        elif tags.get("emergency") == "disaster_help_point":
            shelter_type = "Disaster Help Point"
            verification = "OSM_DISASTER_HELP_POINT"
            priority = 2

        elif tags.get("emergency") == "assembly_point":
            shelter_type = "Emergency Assembly Point"
            verification = "OSM_ASSEMBLY_POINT"
            priority = 3

        elif tags.get("amenity") == "shelter":
            shelter_type = "Mapped Shelter"
            verification = "OSM_GENERAL_SHELTER"
            priority = 4

        else:
            continue

        # -----------------------------------------
        # Name
        # -----------------------------------------

        name = (
            tags.get("name")
            or tags.get("name:en")
            or shelter_type
        )

        # -----------------------------------------
        # Address
        # -----------------------------------------

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:village"),
            tags.get("addr:town"),
            tags.get("addr:city"),
            tags.get("addr:district"),
            tags.get("addr:state"),
        ]

        address = ", ".join(
            part
            for part in address_parts
            if part
        )

        # -----------------------------------------
        # Capacity
        # -----------------------------------------

        capacity = _safe_int(
            tags.get("capacity"),
            0,
        )

        shelters.append({
            "id": f"osm_{element_id}",
            "name": name,
            "location": (
                address
                or "OpenStreetMap location"
            ),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "capacity": capacity,
            "isHighGround": False,

            "source": "OpenStreetMap",

            "verification": verification,

            "shelterType": shelter_type,

            "osmType": element.get("type"),
            "osmId": element.get("id"),

            "operator": tags.get("operator"),
            "phone": tags.get("phone"),
            "website": tags.get("website"),

            "priority": priority,
        })

    # Emergency shelters first.
    # Then disaster help points.
    # Then assembly points.
    # Then general shelters.
    shelters.sort(
        key=lambda shelter: shelter["priority"]
    )

    return {
        "success": True,
        "count": len(shelters),
        "radius": radius,
        "shelters": shelters,
    }
@app.get("/emergency-facilities")
def get_emergency_facilities(
    lat: float,
    lon: float,
    radius: int = 50000,
):
    """
    Find nearby emergency-support facilities.

    These are NOT classified as shelters.
    They are fallback emergency-support locations.
    """

    query = f"""
    [out:json][timeout:60];

    (
      nwr[
        "amenity"="hospital"
      ](around:{radius},{lat},{lon});

      nwr[
        "healthcare"="hospital"
      ](around:{radius},{lat},{lon});

      nwr[
        "amenity"="police"
      ](around:{radius},{lat},{lon});

      nwr[
        "amenity"="fire_station"
      ](around:{radius},{lat},{lon});

      nwr[
        "emergency"="ambulance_station"
      ](around:{radius},{lat},{lon});
    );

    out center tags;
    """

    encoded_query = urllib.parse.urlencode(
        {"data": query}
    ).encode("utf-8")

    urls = [
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
    ]

    last_error = None
    data = None

    for url in urls:
        try:
            data = _overpass_post_ipv4(
                url,
                encoded_query,
            )
            break
        except Exception as e:
            last_error = str(e)

    if data is None:
        return {
            "success": False,
            "error": last_error or "All facility providers failed",
            "facilities": [],
        }

    facilities = []
    seen_ids = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        element_id = (
            f"{element.get('type')}_{element.get('id')}"
        )

        if element_id in seen_ids:
            continue

        seen_ids.add(element_id)

        latitude = element.get("lat")
        longitude = element.get("lon")

        if latitude is None or longitude is None:
            center = element.get("center", {})
            latitude = center.get("lat")
            longitude = center.get("lon")

        if latitude is None or longitude is None:
            continue

        # -----------------------------------------
        # Classify facility
        # -----------------------------------------

        if (
            tags.get("amenity") == "hospital"
            or tags.get("healthcare") == "hospital"
        ):
            facility_type = "Hospital"

        elif tags.get("amenity") == "police":
            facility_type = "Police Station"

        elif tags.get("amenity") == "fire_station":
            facility_type = "Fire Station"

        elif tags.get("emergency") == "ambulance_station":
            facility_type = "Ambulance Station"

        else:
            continue

        name = (
            tags.get("name")
            or tags.get("name:en")
            or facility_type
        )

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:suburb"),
            tags.get("addr:village"),
            tags.get("addr:town"),
            tags.get("addr:city"),
            tags.get("addr:district"),
            tags.get("addr:state"),
        ]

        address = ", ".join(
            part
            for part in address_parts
            if part
        )

        facilities.append({
            "id": f"osm_{element_id}",
            "name": name,
            "type": facility_type,
            "location": (
                address
                or "OpenStreetMap location"
            ),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "phone": tags.get("phone"),
            "website": tags.get("website"),
            "operator": tags.get("operator"),
            "emergency": tags.get("emergency"),
            "source": "OpenStreetMap",
        })

    return {
        "success": True,
        "count": len(facilities),
        "radius": radius,
        "facilities": facilities,
    }

def _safe_int(
    value,
    default=0,
):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _safe_int(
    value,
    default=0,
):
    try:
        return int(value)

    except (TypeError, ValueError):
        return default