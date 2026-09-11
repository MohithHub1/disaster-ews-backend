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
    radius: int = 25000,
):
    """
    Get nearby emergency shelters from OpenStreetMap.
    """

    query = f"""
    [out:json][timeout:25];

    (
      nwr["emergency:social_facility"="shelter"]
        (around:{radius},{lat},{lon});

      nwr["social_facility"="shelter"]
        (around:{radius},{lat},{lon});

      nwr["evacuation_center"="yes"]
        (around:{radius},{lat},{lon});
    );

    out center tags;
    """

    encoded_query = urllib.parse.urlencode(
        {"data": query}
    ).encode("utf-8")

    urls = [
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
            "error": (
                last_error
                or "All shelter providers failed"
            ),
            "shelters": [],
        }

    shelters = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        latitude = element.get("lat")
        longitude = element.get("lon")

        if latitude is None or longitude is None:
            center = element.get("center", {})
            latitude = center.get("lat")
            longitude = center.get("lon")

        if latitude is None or longitude is None:
            continue

        name = (
            tags.get("name")
            or tags.get("name:en")
            or "Emergency Shelter"
        )

        address_parts = [
            tags.get("addr:housenumber"),
            tags.get("addr:street"),
            tags.get("addr:city"),
        ]

        address = ", ".join(
            part
            for part in address_parts
            if part
        )

        shelters.append(
            {
                "id": (
                    f"osm_{element.get('type')}_"
                    f"{element.get('id')}"
                ),
                "name": name,
                "location": (
                    address
                    or "OpenStreetMap location"
                ),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "capacity": _safe_int(
                    tags.get("capacity"),
                    0,
                ),
                "isHighGround": False,
                "source": "OpenStreetMap",
                "osmType": element.get("type"),
                "osmId": element.get("id"),
                "operator": tags.get("operator"),
                "phone": tags.get("phone"),
                "website": tags.get("website"),
            }
        )

    return {
        "success": True,
        "count": len(shelters),
        "radius": radius,
        "shelters": shelters,
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