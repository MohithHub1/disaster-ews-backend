import joblib
import pandas as pd

MODEL_PATH = "models/flood_xgb_model.pkl"

flood_features = [
    "precipitation",
    "antecedent_precip_index",
    "avg_soil_moisture",
    "river_water_level_cm",
    "elevation_m",
    "slope_deg",
    "twi_index",
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
]

flood_model = joblib.load(MODEL_PATH)


def predict_flood(data: dict):
    row = {
        feature: data.get(feature, 0.0)
        for feature in flood_features
    }

    input_df = pd.DataFrame([row])

    probability = float(
        flood_model.predict_proba(input_df)[0][1]
    )

    if probability < 0.25:
        risk = "Low"
    elif probability < 0.50:
        risk = "Moderate"
    elif probability < 0.75:
        risk = "High"
    else:
        risk = "Critical"

    return {
        "flood_probability": round(probability, 4),
        "flood_risk": risk,
    }
