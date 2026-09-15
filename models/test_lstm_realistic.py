import pickle
import tensorflow as tf
import numpy as np


print("Loading scaler...")

with open("models/scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

print("Scaler loaded")


print("Loading LSTM...")

model = tf.keras.models.load_model(
    "models/flood_lstm_model.keras"
)

print("LSTM loaded")


# One realistic environmental row based on the
# training feature distribution.
row = {
    "temperature_2m": 15.0,
    "relative_humidity_2m": 56.0,
    "precipitation": 0.14,
    "rain": 0.10,
    "surface_pressure": 821.8,
    "wind_speed_10m": 4.2,
    "soil_moisture_0_to_7cm": 0.319,
    "soil_moisture_7_to_28cm": 0.318,
    "rain_1h": 0.14,
    "rain_3h": 0.41,
    "rain_6h": 0.83,
    "rain_12h": 1.65,
    "rain_24h": 3.31,
    "antecedent_precip_index": 0.92,
    "avg_soil_moisture": 0.319,
    "latitude": 30.556,
    "longitude": 79.567,
    "elevation_m": 1890.0,
    "slope_deg": 31.5,
    "twi_index": 10.56,
    "river_water_level_cm": 130.4,
    "water_level_lag1h": 130.4,
    "water_level_lag3h": 130.4,
    "soil_moisture_0_to_7cm_change": -0.00001,
    "soil_moisture_7_to_28cm_change": -0.00001,
    "avg_soil_moisture_change": -0.00001,
    "hour": 11.5,
    "day": 15.6,
    "month": 6.34,
    "day_of_week": 3.0,
}


features = list(scaler.feature_names_in_)

values = np.array(
    [[row[feature] for feature in features]],
    dtype=np.float32,
)


scaled = scaler.transform(values)


# Repeat the realistic row for the required
# 12 historical time steps.
sequence = np.repeat(
    scaled,
    12,
    axis=0,
)

sequence = sequence[np.newaxis, :, :]


print("Sequence shape:", sequence.shape)


prediction = model.predict(
    sequence,
    verbose=0,
)


print()
print("LSTM PIPELINE SUCCESSFUL")
print("Flood probability:", float(prediction[0][0]))