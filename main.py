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