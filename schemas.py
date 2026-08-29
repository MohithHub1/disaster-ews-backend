from pydantic import BaseModel


class AssessmentCreate(BaseModel):
    location: str

    rainfall: float
    soil_moisture: float
    water_level: float
    temperature: float
    humidity: float
    wind_speed: float

    slope: float
    historical_disaster: float