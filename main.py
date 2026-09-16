import json
import urllib.parse
import urllib.request
import http.client
import socket
import ssl
import os
import firebase_admin

from firebase_admin import credentials, messaging
from pydantic import BaseModel
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import Base, engine, SessionLocal
from ml_predictor import predict_flood
from soil_type_service import get_soil_type
from landslide_ml_predictor import predict_landslide
from vegetation_service import get_vegetation_cover
from earthquake_service import get_earthquake_activity
from water_proximity_service import get_water_proximity
from historical_disaster_service import get_historical_disaster_risk
from models import Assessment, FcmToken
from schemas import AssessmentCreate
from water_level_service import get_water_level
from datetime import datetime


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
# Firebase Admin SDK
firebase_service_account = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")

if firebase_service_account:
    try:
        service_account_info = json.loads(firebase_service_account)

        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)

        print("FIREBASE ADMIN SDK INITIALIZED")
    except Exception as e:
        print("FIREBASE ADMIN SDK ERROR:", e)
else:
    print("FIREBASE_SERVICE_ACCOUNT_JSON NOT SET")
def send_fcm_notification(token: str, title: str, body: str):
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=token,
        )

        response = messaging.send(message)

        print("FCM NOTIFICATION SENT:", response)

        return {
            "success": True,
            "message_id": response,
        }

    except Exception as e:
        print("FCM NOTIFICATION ERROR:", e)

        return {
            "success": False,
            "error": str(e),
        }
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
@app.post("/test-fcm")
def test_fcm(request: dict):
    token = str(request.get("token") or "").strip()

    if not token:
        return {
            "success": False,
            "message": "FCM token is required",
        }

    return send_fcm_notification(
        token=token,
        title="Disaster EWS Test Alert",
        body="Firebase Cloud Messaging is working successfully.",
    )
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
@app.post("/fcm/register")
def register_fcm_token(
    request: dict,
    db: Session = Depends(get_db),
):
    token = str(request.get("token") or "").strip()
    location = str(request.get("location") or "").strip()

    if not token or not location:
        return {
            "message": "FCM token and location are required",
            "registered": False,
        }

    existing = (
        db.query(FcmToken)
        .filter(FcmToken.token == token)
        .first()
    )

    if existing:
        existing.location = location
        existing.updated_at = datetime.utcnow()
    else:
        db.add(
            FcmToken(
                token=token,
                location=location,
            )
        )

    db.commit()

    return {
        "message": "FCM token registered successfully",
        "location": location,
        "registered": True,
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
    latitude: float | None = None
    longitude: float | None = None
    earthquake_activity: float = 0.0

@app.post('/predict')
def predict(request: FloodPredictionRequest):
    data = request.model_dump()

    # Convert Admin Input values to the units expected by the flood ML model.
    if data["precipitation"] == 0.0:
        data["precipitation"] = data["rainfall"]

    if data["avg_soil_moisture"] == 0.0:
        data["avg_soil_moisture"] = (
            data["soil_moisture"] / 100.0
        )

    # Water level handling:
    # Use the real entered value when available.
    # If unavailable, use the training-data median (125.56 cm)
    # instead of treating missing data as 0 cm.
    if data["river_water_level_cm"] == 0.0:
        if data["water_level"] > 0.0:
            data["river_water_level_cm"] = (
                data["water_level"] * 100.0
            )
        else:
            data["river_water_level_cm"] = 125.56

    if data["temperature_2m"] == 0.0:
        data["temperature_2m"] = data["temperature"]

    if data["relative_humidity_2m"] == 0.0:
        data["relative_humidity_2m"] = data["humidity"]

    if data["wind_speed_10m"] == 0.0:
        data["wind_speed_10m"] = (
            data["wind_speed"] / 3.6
        )

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

    flood_result = predict_flood(data)
    vegetation_cover = 0.0
              
              
    soil_result = {
        "available": False,
        "sand_percent": 0.0,
        "silt_percent": 0.0,
        "clay_percent": 0.0,
        "soil_type": "Unknown",
        "source": "SoilGrids",
    }

    if (
        data.get("latitude") is not None
        and data.get("longitude") is not None
    ):
        try:
            soil_result = get_soil_type(
                latitude=data["latitude"],
                longitude=data["longitude"],
            )

            print(
                "SOIL TYPE:",
                soil_result,
            )

        except Exception as e:
            print(
                f"SOILGRIDS API ERROR: {e}"
            )
    if (
        data.get("latitude") is not None
        and data.get("longitude") is not None
    ):
        try:
            earthquake_result = get_earthquake_activity(
                latitude=data["latitude"],
                longitude=data["longitude"],
            )

            earthquake_activity = float(
                earthquake_result["max_magnitude"]
            )

            print(
                "EARTHQUAKE ACTIVITY:",
                earthquake_activity,
            )

        except Exception as e:
            print(
                f"EARTHQUAKE API ERROR: {e}"
            )

        water_proximity = 0.0

    if (
        data.get("latitude") is not None
        and data.get("longitude") is not None
    ):
        try:
            water_result = get_water_proximity(
                latitude=data["latitude"],
                longitude=data["longitude"],
            )

            if water_result.get("available"):
                distance_km = float(
                    water_result.get("distance_km", 0.0)
                )

                water_proximity = max(
                    0.0,
                    min(
                        2.0,
                        2.0 * (1.0 - distance_km / 5.0),
                    ),
                )

            print(
                "WATER PROXIMITY:",
                water_result,
                "MODEL SCORE:",
                water_proximity,
            )

        except Exception as e:
            print(
                f"WATER PROXIMITY API ERROR: {e}"
            )
    soil_result = {
        "available": False,
        "sand_percent": 0.0,
        "silt_percent": 0.0,
        "clay_percent": 0.0,
        "soil_type": "Unknown",
        "source": "SoilGrids",
    }

    if (
        data.get("latitude") is not None
        and data.get("longitude") is not None
    ):
        try:
            soil_result = get_soil_type(
                latitude=data["latitude"],
                longitude=data["longitude"],
            )

            print(
                "SOIL TYPE:",
                soil_result,
            )

        except Exception as e:
            print(
                f"SOILGRIDS API ERROR: {e}"
            )
    landslide_data = {
        "Rainfall_mm": data["rainfall"],
        "Slope_Angle": data["slope_deg"],
        "Soil_Saturation": data["avg_soil_moisture"],
        "Vegetation_Cover": vegetation_cover,
        "Earthquake_Activity": earthquake_activity,
        "Proximity_to_Water": water_proximity,
          "Soil_Type_Gravel": 1.0 if soil_result["soil_type"] == "Gravel" else 0.0,
"Soil_Type_Sand": 1.0 if soil_result["soil_type"] == "Sand" else 0.0,
"Soil_Type_Silt": 1.0 if soil_result["soil_type"] == "Silt" else 0.0,
    }
    historical_result = {
        "historical_risk": 0.0,
        "event_count": 0,
    }

    if (
        data.get("latitude") is not None
        and data.get("longitude") is not None
    ):
        try:
            historical_result = (
                get_historical_disaster_risk(
                    latitude=data["latitude"],
                    longitude=data["longitude"],
                )
            )

            print(
                "HISTORICAL DISASTER:",
                historical_result,
            )

        except Exception as e:
            print(
                f"HISTORICAL DISASTER API ERROR: {e}"
            )
    landslide_result = predict_landslide(
        landslide_data
    )

    return {
    **flood_result,
    **landslide_result,
    "historical_risk": historical_result.get(
        "historical_risk",
        0.0,
    ),
    "historical_event_count": historical_result.get(
        "event_count",
        0,
    ),
        "soil_type": soil_result.get(
        "soil_type",
        "Unknown",
    ),
    "sand_percent": soil_result.get(
        "sand_percent",
        0.0,
    ),
    "silt_percent": soil_result.get(
        "silt_percent",
        0.0,
    ),
    "clay_percent": soil_result.get(
        "clay_percent",
        0.0,
    ),
}
@app.get("/historical-disaster-risk")
def historical_disaster_risk(
    latitude: float,
    longitude: float,
):
    try:
        result = get_historical_disaster_risk(
            latitude=latitude,
            longitude=longitude,
        )

        return result

    except Exception as e:
        print(
            f"HISTORICAL DISASTER ENDPOINT ERROR: {e}"
        )

        return {
            "historical_risk": 0.0,
            "event_count": 0,
            "search_years": 5,
            "radius_km": 100.0,
            "events": [],
            "source": "GDACS",
            "available": False,
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
@app.get("/water-level")
def water_level(
    latitude: float,
    longitude: float,
):
    try:
        with open(
            "water_level_stations.json",
            "r",
            encoding="utf-8",
        ) as file:
            stations = json.load(file)

        return get_water_level(
            latitude=latitude,
            longitude=longitude,
            stations=stations,
        )

    except FileNotFoundError:
        return {
            "available": False,
            "reason": (
                "Water-level station database "
                "is not available."
            ),
        }

    except Exception as e:
        return {
            "available": False,
            "reason": f"Water-level lookup failed: {e}",
        }