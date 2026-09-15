import joblib
import pickle
import xgboost


def capture_setstate(self, state):
    self.__dict__.update(state)


# Bypass broken XGBoost Booster deserialization
xgboost.Booster.__setstate__ = capture_setstate


print("Loading backend_models.pkl...")

with open("models/backend_models.pkl", "rb") as f:
    models = joblib.load(f)

print("PKL loaded successfully")


# ------------------------------------------------------------
# Extract StandardScaler
# ------------------------------------------------------------

scaler = models["scaler"]

with open("models/scaler.pkl", "wb") as f:
    pickle.dump(scaler, f)

print("SCALER EXTRACTED")
print("Scaler features:", len(scaler.feature_names_in_))


# ------------------------------------------------------------
# Extract metadata
# ------------------------------------------------------------

metadata = {
    "flood_features": models["flood_features"],
    "landslide_features": models["landslide_features"],
    "lstm_features": models["lstm_features"],
    "lstm_sequence_length": models["lstm_sequence_length"],
    "xgb_weight": models["xgb_weight"],
    "lstm_weight": models["lstm_weight"],
    "fusion_threshold": models["fusion_threshold"],
}

with open("models/ml_metadata.pkl", "wb") as f:
    pickle.dump(metadata, f)

print("METADATA EXTRACTED")

print("Sequence length:", metadata["lstm_sequence_length"])
print("XGB weight:", metadata["xgb_weight"])
print("LSTM weight:", metadata["lstm_weight"])
print("Fusion threshold:", metadata["fusion_threshold"])

print("DONE")