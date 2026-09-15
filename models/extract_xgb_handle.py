import joblib
import xgboost


# Prevent XGBoost from trying to deserialize the Booster
# while joblib reconstructs the rest of the model.
original_setstate = xgboost.Booster.__setstate__


def capture_setstate(self, state):
    self.__dict__.update(state)


xgboost.Booster.__setstate__ = capture_setstate


print("Loading backend_models.pkl...")

models = joblib.load("models/backend_models.pkl")

print("PKL LOADED")

print("Keys:")
print(models.keys())

flood_model = models["flood_xgb_model"]

print("Flood model type:")
print(type(flood_model))

print("Flood model attributes:")
print(flood_model.__dict__.keys())

booster = flood_model.get_booster()

print("Booster type:")
print(type(booster))

print("Booster attributes:")
print(booster.__dict__.keys())

handle = booster.__dict__.get("handle")

print("Handle type:")
print(type(handle))

if handle is None:
    print("ERROR: No handle found")
else:
    print("Handle size:", len(handle))

    with open("models/flood_xgb_handle.bin", "wb") as f:
        f.write(handle)

    print("HANDLE EXTRACTED")