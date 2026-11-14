"""Python bindings for the C++ library in ``cpp/`` (loaded with ctypes).

Every function declared in ``cpp/include/fieldshift/fieldshift.h`` gets a
Python wrapper here. When the library has not been built the module still
imports; ``is_available()`` returns False and the wrappers raise RuntimeError.
"""

import ctypes
import os
import sys
from pathlib import Path

# repository root (two levels above this package)
_ROOT = Path(__file__).resolve().parents[2]

# file name of the shared library on this platform
_LIB_NAME = {"win32": "fieldshift_core.dll",
             "darwin": "libfieldshift_core.dylib"}.get(sys.platform, "libfieldshift_core.so")

_lib = None


# ()
# loads the shared library once: $FIELDSHIFT_CORE_LIB, then cpp/build/, then
# the system search path. returns the ctypes library or None
def _load():
    global _lib
    if _lib is not None:
        return _lib
    candidates = [os.environ.get("FIELDSHIFT_CORE_LIB"),
                  _ROOT / "cpp" / "build" / _LIB_NAME,
                  _ROOT / "cpp" / "build" / "Release" / _LIB_NAME,
                  _LIB_NAME]
    for path in filter(None, candidates):
        try:
            lib = ctypes.CDLL(str(path))
        except OSError:
            continue
        _declare(lib)
        _lib = lib
        return lib
    return None


# (CDLL lib)
# sets argtypes / restype for every exported function (keep in sync with the header)
def _declare(lib):
    dbl = ctypes.c_double
    dbl_p = ctypes.POINTER(ctypes.c_double)
    lib.fs_version.argtypes = []
    lib.fs_version.restype = ctypes.c_char_p
    lib.fs_haversine_km.argtypes = [dbl, dbl, dbl, dbl]
    lib.fs_haversine_km.restype = dbl
    lib.fs_ndvi.argtypes = [dbl, dbl]
    lib.fs_ndvi.restype = dbl
    lib.fs_ndvi_array.argtypes = [dbl_p, dbl_p, dbl_p, ctypes.c_size_t]
    lib.fs_ndvi_array.restype = ctypes.c_int


def _require():
    lib = _load()
    if lib is None:
        raise RuntimeError("fieldshift C++ core not built: run `make cpp`")
    return lib


# ()
# True when the C++ library could be loaded
def is_available():
    return _load() is not None


# ()
# version string reported by the C++ library
def version():
    return _require().fs_version().decode()


# (float lat1, float lon1, float lat2, float lon2)
# great-circle distance in kilometres between two points in degrees
def haversine_km(lat1, lon1, lat2, lon2):
    return _require().fs_haversine_km(lat1, lon1, lat2, lon2)


# (float nir, float red)
# normalised difference vegetation index (nir - red) / (nir + red)
def ndvi(nir, red):
    return _require().fs_ndvi(nir, red)


# (sequence nir, sequence red)
# NDVI of two equally long sequences; returns a list of floats
def ndvi_array(nir, red):
    if len(nir) != len(red):
        raise ValueError("nir and red must have the same length")
    n = len(nir)
    arr = ctypes.c_double * n
    out = arr()
    rc = _require().fs_ndvi_array(arr(*nir), arr(*red), out, n)
    if rc != 0:
        raise RuntimeError(f"fs_ndvi_array failed with code {rc}")
    return list(out)
