import io
import pickle
import xgboost as xgb


class DummyBooster:
    def __init__(self, *args, **kwargs):
        self.state = None

    def __setstate__(self, state):
        self.state = state


original_booster = xgb.Booster
xgb.Booster = DummyBooster

try:
    with open("models/backend_models.pkl", "rb") as f:
        data = f.read()

    print("PKL size:", len(data))
    print("XGBoost Booster found:", b"xgboost.core" in data)

    obj = pickle.Unpickler(io.BytesIO(data)).load()

    print("Pickle parsed successfully")
    print("Keys:", obj.keys())

    flood = obj["flood_xgb_model"]

    print("Flood model type:", type(flood))
    print("Flood model attributes:", flood.__dict__.keys())

finally:
    xgb.Booster = original_booster