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

**micromamba + conda-forge (Linux, no compiling, recommended)**

Prebuilt QGIS 4 with Python bindings, installed in your home directory and
independent of the system packages. `make run` detects it automatically.

```bash
mkdir -p ~/.local/bin && curl -L https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.10.0-0.tar.bz2 | tar -xj -C ~/.local bin/micromamba
```

```bash
make env
```

```bash
make run
```

`make env` creates `~/micromamba/envs/fieldshift` (about 1–2 GB).
`make which` shows which Python and QGIS `make run` will use;
`make run CONDA=0` forces the system Python. Override the locations with
`MAMBA=`, `MAMBA_ROOT=` and `ENV_NAME=`.

**Conda (any OS)**

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

## QGIS is not found

If the map area says QGIS could not be imported, the Python running the app
cannot `import qgis`. The panel and the terminal show which interpreter was
used and the exact error. Check with the same interpreter:

```bash
python3 -c "import sys; print(sys.executable, sys.version); import qgis.core; print(qgis.core.Qgis.version())"
```

Typical causes:

- **QGIS was built without Python bindings.**
- **The bindings exist for a different Python version** than the `python3`
  you run (e.g. QGIS built for 3.12, `python3` is 3.13). Run the app with
  the matching one: `make run PYTHON=python3.12`.
- **A virtualenv** hides system packages. Create it with
  `--system-site-packages`, or run outside it.
- **Error inside the bindings** (e.g. `No module named 'PyQt6.sip'`): PyQt6
  is missing or built for another Python version.

### Gentoo

Easiest: use the micromamba route above (`make env`), no rebuild needed.
To use the Portage package instead:

QGIS is `sci-geosciences/qgis`; the Python bindings need `USE=python`, and
they are built only for its `PYTHON_SINGLE_TARGET`.

```bash
emerge -pv sci-geosciences/qgis
```

The output must show `python` enabled and which `python_single_target_python3_X`
is set. To see where the bindings went:

```bash
qlist sci-geosciences/qgis | grep -m1 "site-packages/qgis/"
```

Run the app with that Python version, e.g. `make run PYTHON=python3.12`
(Gentoo's `python3` follows `eselect python`, which may be another version).
If `python` was off, enable it and rebuild:

```bash
echo "sci-geosciences/qgis python" | sudo tee -a /etc/portage/package.use/qgis
```

```bash
sudo emerge -av --oneshot sci-geosciences/qgis
```

PyQt6 must be built for the same Python (`dev-python/pyqt6`, pulled in by
`USE=python`).

## Other requirements

- CMake ≥ 3.14 and a C++17 compiler, for `make cpp` (optional).
- Emacs ≥ 27.1, for `make docs-cpp` (optional; minidoc is downloaded
  automatically into `.tools/`).

## Common commands

| Command | Does |
|---------|------|
| `make env` | create the micromamba environment with QGIS 4 |
| `make run` | start the app (inside that environment when it exists) |
| `make which` | show the Python / QGIS `make run` uses |
| `make cpp` | build `cpp/build/libfieldshift_core.so` |
| `make test` | run the tests |
| `make docs` | regenerate `docs/api/` |
