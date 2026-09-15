import ctypes
import xgboost
from xgboost.core import _LIB, _check_call, c_bst_ulong


with open("models/flood_xgb_handle.bin", "rb") as f:
    buf = bytearray(f.read())

print("XGBoost:", xgboost.__version__)
print("Buffer size:", len(buf))
print("First bytes:", bytes(buf[:20]))

handle = ctypes.c_void_p()

_check_call(
    _LIB.XGBoosterCreate(
        None,
        c_bst_ulong(0),
        ctypes.byref(handle),
    )
)

ptr = (ctypes.c_char * len(buf)).from_buffer(buf)

_check_call(
    _LIB.XGBoosterUnserializeFromBuffer(
        handle,
        ptr,
        c_bst_ulong(len(buf)),
    )
)

print("XGB BUFFER RECOVERED")