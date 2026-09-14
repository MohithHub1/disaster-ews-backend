import joblib
import pandas as pd

MODEL_PATH = "models/landslide_xgb_model.pkl"

landslide_features = [
    "Rainfall_mm",
    "Slope_Angle",
    "Soil_Saturation",
    "Vegetation_Cover",
    "Earthquake_Activity",
    "Proximity_to_Water",
    "Soil_Type_Gravel",
    "Soil_Type_Sand",
    "Soil_Type_Silt",
]

landslide_model = joblib.load(MODEL_PATH)


def predict_landslide(data: dict):
    row = {
        feature: data.get(feature, 0.0)
        for feature in landslide_features
    }

    input_df = pd.DataFrame([row])

    probability = float(
        landslide_model.predict_proba(input_df)[0][1]
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
        "landslide_probability": round(probability, 4),
        "landslide_risk": risk,
    }
