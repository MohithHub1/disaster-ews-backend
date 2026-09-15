import xgboost as xgb
from pathlib import Path

path = Path("models/flood_xgb_handle.bin")

data = path.read_bytes()

print("FILE SIZE:", len(data))
print("FIRST BYTES:", data[:32])

booster = xgb.Booster()

try:
    booster.load_model(str(path))
    print("XGBOOST MODEL LOADED")
    print("FEATURE COUNT:", booster.num_features())
except Exception as e:
    print("XGBOOST LOAD FAILED")
    print(type(e).__name__)
    print(e)