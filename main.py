import json
import urllib.parse
import urllib.request
import http.client
import socket
import ssl

from pydantic import BaseModel
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import Base, engine, SessionLocal
from ml_predictor import predict_flood
from landslide_ml_predictor import predict_landslide
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
class FloodPredictionRequest(BaseModel):
    # Admin Input values
    location: str = ""
    rainfall: float = 0.0
    soil_moisture: float = 0.0
    water_level: float = 0.0
    slope_stability: float = 0.0
    historical_risk: float = 0.0
    temperature: float = 0.0
    humidity: float = 0.0
    wind_speed: float = 0.0

    # Direct ML features
    precipitation: float = 0.0
    antecedent_precip_index: float = 0.0
    avg_soil_moisture: float = 0.0
    river_water_level_cm: float = 0.0
    elevation_m: float = 0.0
    slope_deg: float = 0.0
    twi_index: float = 0.0
    temperature_2m: float = 0.0
    relative_humidity_2m: float = 0.0
    surface_pressure: float = 0.0
    wind_speed_10m: float = 0.0

@app.post('/predict')
def predict(request: FloodPredictionRequest):
    data = request.model_dump()

    # Convert Admin Input values to the units expected by the flood ML model.
    if data["precipitation"] == 0.0:
        data["precipitation"] = data["rainfall"]

    if data["avg_soil_moisture"] == 0.0:
        data["avg_soil_moisture"] = data["soil_moisture"] / 100.0

    if data["river_water_level_cm"] == 0.0:
        data["river_water_level_cm"] = data["water_level"] * 100.0

    if data["temperature_2m"] == 0.0:
        data["temperature_2m"] = data["temperature"]

    if data["relative_humidity_2m"] == 0.0:
        data["relative_humidity_2m"] = data["humidity"]

    if data["wind_speed_10m"] == 0.0:
        data["wind_speed_10m"] = data["wind_speed"] / 3.6

    if data["antecedent_precip_index"] == 0.0:
        data["antecedent_precip_index"] = data["rainfall"]

    if data["elevation_m"] == 0.0:
        data["elevation_m"] = 0.0

    if data["slope_deg"] == 0.0:
        data["slope_deg"] = 0.0

    if data["twi_index"] == 0.0:
        data["twi_index"] = 0.0

    if data["surface_pressure"] == 0.0:
        data["surface_pressure"] = 1013.25

    # Run flood ML model.
    flood_result = predict_flood(data)

    # Run landslide ML model.
    landslide_data = {
        "Rainfall_mm": data["rainfall"],
        "Slope_Angle": 0.0,
        "Soil_Saturation": data["avg_soil_moisture"],
        "Vegetation_Cover": 0.0,
        "Earthquake_Activity": 0.0,
        "Proximity_to_Water": 0.0,
        "Soil_Type_Gravel": 0.0,
        "Soil_Type_Sand": 0.0,
        "Soil_Type_Silt": 0.0,
    }

    landslide_result = predict_landslide(landslide_data)

    return {
        **flood_result,
        **landslide_result,
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
@app.get("/assessments")
def get_assessments(
    db: Session = Depends(get_db),
):
    assessments = (
        db.query(Assessment)
        .order_by(Assessment.created_at.desc())
        .all()
    )

    return [
        {
            "id": assessment.id,
            "location": assessment.location,
            "rainfall": assessment.rainfall,
            "risk_level": assessment.risk_level,
            "overall_risk": assessment.overall_risk,
            "flood_risk": assessment.flood_risk,
            "landslide_risk": assessment.landslide_risk,
            "lead_time_minutes": assessment.lead_time_minutes,
            "recommended_action": assessment.recommended_action,
            "soil_moisture": assessment.soil_moisture,
            "water_level": assessment.water_level,
            "temperature": assessment.temperature,
            "humidity": assessment.humidity,
            "wind_speed": assessment.wind_speed,
            "slope": assessment.slope,
            "historical_disaster": assessment.historical_disaster,
            "created_at": assessment.created_at.isoformat()
            if assessment.created_at
            else None,
        }
        for assessment in assessments
    ]
@app.get("/shelters")
def get_shelters(
    lat: float,
    lon: float,
    radius: int = 50000,
):
    """
    Find designated emergency shelters / evacuation centres
    near a location.

    Only explicit emergency shelter classifications are used.
    General OSM shelters and assembly points are excluded.
    """

    query = f"""
[out:json][timeout:60];

(
  nwr[
    "emergency:social_facility"="shelter"
  ](around:{radius},{lat},{lon});

  nwr[
    "amenity"="social_facility"
  ][
    "social_facility"="shelter"
  ](around:{radius},{lat},{lon});

  nwr[
    "evacuation_center"="yes"
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
        # Classify verified emergency shelter
        # -----------------------------------------

        if (
            tags.get("emergency:social_facility")
            == "shelter"
        ):
            shelter_type = "Emergency Shelter"
            verification = "OSM_EMERGENCY_SHELTER"
            priority = 1

        elif (
            tags.get("social_facility")
            == "shelter"
        ):
            shelter_type = "Emergency Shelter"
            verification = "OSM_SOCIAL_SHELTER"
            priority = 1

        elif (
            tags.get("evacuation_center")
            == "yes"
        ):
            shelter_type = "Evacuation Centre"
            verification = "OSM_EVACUATION_CENTRE"
            priority = 1

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