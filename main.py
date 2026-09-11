import json
import urllib.parse
import urllib.request

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


# ============================================================
# GET ASSESSMENTS
# ============================================================

@app.get("/assessments")
def get_assessments(
    db: Session = Depends(get_db),
):
    return (
        db.query(Assessment)
        .order_by(Assessment.id.desc())
        .all()
    )


# ============================================================
# GET NEARBY REAL-WORLD SHELTERS
# ============================================================

@app.get("/shelters")
def get_shelters(
    lat: float,
    lon: float,
    radius: int = 25000,
):
    """
    Get nearby emergency shelters from OpenStreetMap.

    lat    = user's latitude
    lon    = user's longitude
    radius = search radius in metres
    """

    # --------------------------------------------------------
    # OPENSTREETMAP OVERPASS QUERY
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # OVERPASS SERVERS
    # --------------------------------------------------------

    urls = [
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ]


    # --------------------------------------------------------
    # TRY OVERPASS SERVERS
    # --------------------------------------------------------

    last_error = None
    data = None

    for url in urls:

        try:
            request = urllib.request.Request(
                url,
                data=encoded_query,
                headers={
                    "User-Agent": "DisasterEWS/1.0",
                    "Content-Type": (
                        "application/x-www-form-urlencoded"
                    ),
                },
                method="POST",
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

            # Successful request
            break

        except Exception as e:
            last_error = str(e)


    # --------------------------------------------------------
    # IF ALL SERVERS FAILED
    # --------------------------------------------------------

    if data is None:
        return {
            "success": False,
            "error": (
                last_error
                or "All shelter providers failed"
            ),
            "shelters": [],
        }


    # --------------------------------------------------------
    # PROCESS SHELTERS
    # --------------------------------------------------------

    shelters = []

    for element in data.get("elements", []):

        tags = element.get("tags", {})


        # ----------------------------------------------------
        # GET COORDINATES
        # ----------------------------------------------------

        latitude = element.get("lat")
        longitude = element.get("lon")


        # Ways / relations use center coordinates
        if latitude is None or longitude is None:

            center = element.get(
                "center",
                {}
            )

            latitude = center.get("lat")
            longitude = center.get("lon")


        # Skip invalid locations
        if latitude is None or longitude is None:
            continue


        # ----------------------------------------------------
        # SHELTER NAME
        # ----------------------------------------------------

        name = (
            tags.get("name")
            or tags.get("name:en")
            or "Emergency Shelter"
        )


        # ----------------------------------------------------
        # ADDRESS
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # ADD SHELTER
        # ----------------------------------------------------

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

                "operator": tags.get(
                    "operator"
                ),

                "phone": tags.get(
                    "phone"
                ),

                "website": tags.get(
                    "website"
                ),
            }
        )


    # --------------------------------------------------------
    # RETURN RESULT
    # --------------------------------------------------------

    return {
        "success": True,
        "count": len(shelters),
        "radius": radius,
        "shelters": shelters,
    }


# ============================================================
# SAFE INTEGER CONVERSION
# ============================================================

def _safe_int(
    value,
    default=0,
):
    try:
        return int(value)

    except (TypeError, ValueError):
        return default