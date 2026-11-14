# Field Shift documentation

| Page | What it covers |
|------|----------------|
| [architecture.md](architecture.md) | How the pieces fit together |
| [map-abstraction.md](map-abstraction.md) | `MapView` / `LayerSpec` API, adding a map backend |
| [cpp.md](cpp.md) | Writing C++ functions and calling them from Python |
| [minidoc.md](minidoc.md) | How code is documented and how `docs/api/` is generated |
| [contributing.md](contributing.md) | Workflow, adding a panel feature, tests |
| [api/PYTHON_API.md](api/PYTHON_API.md) | Generated reference of the Python code |
| [api/CPP_API.md](api/CPP_API.md) | Generated reference of the C++ code |

## Installing QGIS

QGIS brings its own Python bindings and PyQt5; they cannot be installed with
`pip`. Run the app with the Python interpreter that can `import qgis`.

**Conda (any OS, recommended for development)**

```bash
conda create -n fieldshift -c conda-forge qgis python=3.12
```

```bash
conda activate fieldshift
```

**Debian / Ubuntu**

```bash
sudo apt install python3-qgis qgis-providers
```

On Ubuntu use the system interpreter (`/usr/bin/python3`): a Python
installed elsewhere will not see `qgis`. If your default `python3` is a
different one, run `make run PYTHON=/usr/bin/python3`.

**Windows / macOS installers**

Install QGIS from <https://qgis.org>, then start the app from the *OSGeo4W
Shell* (Windows) or with the Python inside the app bundle (macOS,
`/Applications/QGIS.app/Contents/MacOS/bin/python3`). If QGIS cannot find its
resources, set `QGIS_PREFIX_PATH` to the QGIS install directory.

Check it works:

```bash
python3 -c "from qgis.core import Qgis; print(Qgis.QGIS_VERSION)"
```

Without QGIS, the window still opens (with PyQt5 installed) and shows a
placeholder instead of the map, which is enough to work on the panel.

## Other requirements

- CMake ≥ 3.14 and a C++17 compiler, for `make cpp` (optional).
- Emacs ≥ 27.1, for `make docs-cpp` (optional; minidoc is downloaded
  automatically into `.tools/`).

## Common commands

| Command | Does |
|---------|------|
| `make run` | start the app |
| `make cpp` | build `cpp/build/libfieldshift_core.so` |
| `make test` | run the tests |
| `make docs` | regenerate `docs/api/` |
