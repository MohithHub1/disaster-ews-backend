import joblib
import xgboost
from xgboost.core import _LIB, _check_call
import ctypes


# Prevent joblib from trying to deserialize the Booster normally.
def capture_setstate(self, state):
    self.__dict__.update(state)


xgboost.Booster.__setstate__ = capture_setstate


print("Loading backend_models.pkl...")

models = joblib.load("models/backend_models.pkl")

booster = models["landslide_model"]._Booster
handle = booster.__dict__["handle"]

print("PKL LOADED")
print("Handle type:", type(handle))
print("Handle size:", len(handle))


# Try XGBoost's native buffer deserialization.
new_booster = xgboost.Booster()
length = xgboost.core.c_bst_ulong(len(handle))
buffer = (ctypes.c_char * len(handle)).from_buffer_copy(handle)

result = _LIB.XGBoosterUnserializeFromBuffer(
    new_booster.handle,
    buffer,
    length,
)

_check_call(result)

print("BUFFER RECOVERY SUCCESSFUL")
print("Recovered Booster:", new_booster)