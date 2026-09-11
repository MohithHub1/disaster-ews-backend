import json
import urllib.parse
import urllib.request
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal
from models import Assessment
from schemas import AssessmentCreate
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
# Create database tables
Base.metadata.create_all(bind=engine)

# Add new assessment columns to existing databases
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

app = FastAPI(title="Disaster Early Warning System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "message": "Disaster EWS backend is running"
    }


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


@app.get("/assessments")
def get_assessments(db: Session = Depends(get_db)):
    return db.query(Assessment).order_by(Assessment.id.desc()).all()
@app.get("/shelters")
def get_shelters(
    lat: float,
    lon: float,
    radius: int = 25000,
):
    """
    Get nearby real-world emergency shelters from OpenStreetMap.

    lat     = user's latitude
    lon     = user's longitude
    radius  = search radius in metres
    """

    # OpenStreetMap Overpass query.
    #
    # We intentionally prioritize actual emergency/shelter tags
    # instead of ordinary bus shelters.
    query = f"""
    [out:json][timeout:25];

    (
      nwr["emergency:social_facility"="shelter"](around:{radius},{lat},{lon});
      nwr["social_facility"="shelter"](around:{radius},{lat},{lon});
      nwr["evacuation_center"="yes"](around:{radius},{lat},{lon});
    );

    out center tags;
    """

    encoded_query = urllib.parse.urlencode(
        {"data": query}
    ).encode("utf-8")

    url = "https://overpass-api.de/api/interpreter"

    request = urllib.request.Request(
        url,
        data=encoded_query,
        headers={
            "User-Agent": "DisasterEWS/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "shelters": [],
        }

    shelters = []

    for element in data.get("elements", []):
        tags = element.get("tags", {})

        # Nodes have lat/lon directly.
        latitude = element.get("lat")
        longitude = element.get("lon")

        # Ways/relations normally provide a center.
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
            part for part in address_parts if part
        )

        shelters.append({
            "id": f"osm_{element.get('type')}_{element.get('id')}",
            "name": name,
            "location": address or "OpenStreetMap location",
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
        })

    return {
        "success": True,
        "count": len(shelters),
        "radius": radius,
        "shelters": shelters,
    }


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default