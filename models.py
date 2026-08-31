from sqlalchemy import Column, DateTime, Float, Integer, String
from datetime import datetime

from database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)

    location = Column(String, nullable=False)
    risk_level = Column(String, nullable=True)
    overall_risk = Column(Float, nullable=True)
    flood_risk = Column(Float, nullable=True)
    landslide_risk = Column(Float, nullable=True)
    lead_time_minutes = Column(Integer, nullable=True)
    recommended_action = Column(String, nullable=True)

    rainfall = Column(Float, nullable=False)
    soil_moisture = Column(Float, nullable=False)
    water_level = Column(Float, nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    wind_speed = Column(Float, nullable=False)

    slope = Column(Float, nullable=False)
    historical_disaster = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)