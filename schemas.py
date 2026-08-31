from pydantic import BaseModel


class AssessmentCreate(BaseModel):
    location: str

    risk_level: str | None = None
    overall_risk: float | None = None
    flood_risk: float | None = None
    landslide_risk: float | None = None
    lead_time_minutes: int | None = None
    recommended_action: str | None = None

    rainfall: float
    soil_moisture: float
    water_level: float
    temperature: float
    humidity: float
    wind_speed: float

    slope: float
    historical_disaster: float