# NasaSpace-Apps-2026
This is the official Nasa Space Apps 2026 Repository for the contributions of the Ursa Crux Rocketry club located in Pontificia Universidad Católica de Chile. This repository contains the solution to the challenge Field Shift: Adapting farmers with Nasa Data

![Field Shift main window](docs/images/screenshot.png)

**Field Shift** is a Python desktop app built on top of **QGIS 4 (Qt6)**: a map on the
left, a panel on the right. The map is hidden behind an abstraction layer
(`fieldshift/map/`), so new features never call QGIS directly, and
performance-critical code can be written in C++ (`cpp/`) and called from
Python.

## Quick start

```bash
# 1. install QGIS 4 with its Python bindings (see docs/README.md for your OS)
# 2. optional: build the C++ core
make cpp
# 3. run
make run            # or: python3 -m fieldshift
```

## Layout

```
fieldshift/            Python application
├── app.py             start-up: QgsApplication, default layers, window
├── map/               map abstraction layer (MapView, LayerSpec, Event)
│   ├── view.py        abstract MapView: the only map API the UI uses
│   ├── qgis_view.py   QGIS implementation (QgsMapCanvas)
│   └── placeholder_view.py   used when QGIS is not installed
├── ui/                main window (map left, panel right), side panel, fields box
├── fields/            saved fields (farm plots) as GeoJSON, no Qt/QGIS needed
├── i18n/              user-visible texts per language (en.json, es.json)
└── native/            ctypes bindings for the C++ library
cpp/                   C++ functions callable from Python (CMake)
data/                  bundled datasets (offline country outlines)
docs/                  documentation, generated API reference in docs/api/
tools/minidoc_py.py    minidoc-style exporter for the Python code
tests/                 unit tests (python -m unittest)
```

## Documentation

Start at [docs/README.md](docs/README.md):
[architecture](docs/architecture.md) ·
[map abstraction layer](docs/map-abstraction.md) ·
[C++ functions](docs/cpp.md) ·
[documenting with minidoc](docs/minidoc.md) ·
[contributing](docs/contributing.md) ·
API reference: [Python](docs/api/PYTHON_API.md), [C++](docs/api/CPP_API.md).
