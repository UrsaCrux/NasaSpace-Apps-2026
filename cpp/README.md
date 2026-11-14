# cpp/ — C++ functions for the Python scripts

```
cpp/
├── CMakeLists.txt              builds every src/*.cpp into one shared library
├── include/fieldshift/         declarations (the API Python sees)
│   └── fieldshift.h
└── src/                        definitions
    └── fieldshift.cpp
```

Build (from the repository root):

```bash
make cpp
```

This produces `cpp/build/libfieldshift_core.so` (`.dylib` on macOS,
`fieldshift_core.dll` on Windows). `fieldshift/native/__init__.py` loads it
with `ctypes`; set `FIELDSHIFT_CORE_LIB=/path/to/lib` to load it from
elsewhere.

Use from Python:

```python
from fieldshift import native

if native.is_available():
    print(native.ndvi(0.6, 0.2))          # 0.5
    print(native.haversine_km(-33.45, -70.66, -36.82, -73.05))
```

## Adding a function

1. **Declare** it in `include/fieldshift/fieldshift.h`, inside the
   `extern "C"` block, with `FS_API`, and a minidoc comment directly above it:

   ```cpp
   // (double tmax, double tmin, double tbase)
   // growing degree days of one day, never negative
   FS_API double fs_growing_degree_days(double tmax, double tmin, double tbase);
   ```

2. **Define** it in a file under `src/` (a new file is picked up automatically).
3. **Bind** it in `fieldshift/native/__init__.py`: add `argtypes`/`restype` in
   `_declare()` and a small Python wrapper.
4. `make cpp && make test`.

Rules: only C types cross the boundary (`int`, `double`, `size_t`, pointers,
`const char*`). Keep C++ classes, exceptions and STL types inside `src/`.
Arrays are passed as pointer + length, and the caller owns the memory.
See `docs/cpp.md` for details.
