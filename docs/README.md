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

## Installing QGIS 4

Field Shift targets **QGIS 4**, which is built on **Qt6 / PyQt6**. QGIS 3
(Qt5) is not supported: the app prints a warning at start-up if it finds it.

QGIS brings its own Python bindings and PyQt6; they cannot be installed with
`pip`. Run the app with the Python interpreter that can `import qgis`.

**Conda (any OS, recommended for development)**

```bash
conda create -n fieldshift -c conda-forge "qgis>=4" python=3.12
```

```bash
conda activate fieldshift
```

Always run the app from the **activated** environment: activation puts the
QGIS bindings (`$CONDA_PREFIX/share/qgis/python`) on `PYTHONPATH`. Calling
the environment's `python` directly without activating gives
`No module named 'qgis'`. Tested with QGIS 4.2.3 / Qt 6.11.3 from conda-forge.

**Debian / Ubuntu**

The distribution packages may still be QGIS 3. Add the official QGIS
repository first (instructions at <https://qgis.org/resources/installation-guide/>),
then:

```bash
sudo apt install python3-qgis qgis-providers
```

Use the system interpreter (`/usr/bin/python3`): a Python installed elsewhere
will not see `qgis`. If your default `python3` is a different one, run
`make run PYTHON=/usr/bin/python3`.

**Windows / macOS installers**

Install QGIS 4 from <https://qgis.org>, then start the app from the *OSGeo4W
Shell* (Windows) or with the Python inside the app bundle (macOS,
`/Applications/QGIS.app/Contents/MacOS/bin/python3`). If QGIS cannot find its
resources, set `QGIS_PREFIX_PATH` to the QGIS install directory.

Check it works:

```bash
python3 -c "from qgis.core import Qgis; from qgis.PyQt.QtCore import qVersion; print(Qgis.version(), 'Qt', qVersion())"
```

It should print `4.x` and `Qt 6.x`.

Without QGIS, the window still opens (with `pip install PyQt6`) and shows a
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
