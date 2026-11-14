# C++ functions for Python

Everything lives in [`cpp/`](../cpp); see [`cpp/README.md`](../cpp/README.md)
for the step-by-step recipe. This page explains the design.

## Why ctypes and `extern "C"`

The library exposes a plain C API, loaded at run time with Python's built-in
`ctypes`. That means:

- no extra Python dependency and no compile step tied to a Python version;
- the same `.so` works for every interpreter (system, conda, OSGeo4W);
- the app still starts when the library has not been built
  (`native.is_available()` is `False`).

Inside `src/` you can use any C++17: classes, the STL, exceptions. Only the
declarations in `include/fieldshift/fieldshift.h` are visible from Python,
and they must use C types.

## Types across the boundary

| C | ctypes | Python |
|---|--------|--------|
| `int` | `c_int` | `int` |
| `double` | `c_double` | `float` |
| `size_t` | `c_size_t` | `int` |
| `const char*` (returned, static) | `c_char_p` | `bytes` → `.decode()` |
| `const double*` + `size_t n` | `POINTER(c_double)` | list / array |

- Arrays: pointer + length, memory allocated by Python
  (see `fs_ndvi_array` / `native.ndvi_array`).
- Errors: return an `int` code (0 = success); never let a C++ exception
  escape an `extern "C"` function, catch it and return a code.
- Strings returned to Python must be static or owned by the library.

## Current functions

| C | Python |
|---|--------|
| `fs_version()` | `native.version()` |
| `fs_haversine_km(lat1, lon1, lat2, lon2)` | `native.haversine_km(...)` |
| `fs_ndvi(nir, red)` | `native.ndvi(nir, red)` |
| `fs_ndvi_array(nir, red, out, n)` | `native.ndvi_array(nir, red)` |

Generated reference: [api/CPP_API.md](api/CPP_API.md).

## Large rasters

For big arrays, pass NumPy buffers without copying:

```python
import numpy as np, ctypes
nir = np.ascontiguousarray(nir, dtype=np.float64)
ptr = nir.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
```
