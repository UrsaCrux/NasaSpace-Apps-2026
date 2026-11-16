Field Shift {version} — {platform}
=====================================

A desktop decision-support tool for farmers (NASA Space Apps 2026, "Field
Shift: Adapting Farms with NASA Data"), by the Ursa Crux Rocketry club,
Pontificia Universidad Católica de Chile.

This folder contains everything the program needs (QGIS 4, Qt6, Python and
the data libraries): nothing else has to be installed. An internet
connection is needed for the satellite map and the data sources.

START
  Windows : double-click FieldShift.bat
  Linux   : double-click FieldShift.sh (or run ./FieldShift.sh in a terminal)
  macOS   : (local builds only) double-click FieldShift.command. The first
            time macOS may refuse to open it because it is not signed:
            right-click it -> Open, or run in a terminal, inside this folder:
                xattr -dr com.apple.quarantine .

The first start takes about a minute (it prepares the bundled runtime for
this folder); later starts are quick. Keep the folder together: move the
whole folder, not just the launcher. If you move it after the first start,
delete runtime/.unpacked so it is prepared again.

YOUR FIELDS are saved in app/terrenos/ (one GeoJSON file per field). Copy
that folder to keep them when you install a newer version.

LANGUAGE: Spanish with --lang es, English with --lang en (default: English),
e.g.  ./FieldShift.sh --lang es

Optional keys for more data sources (ERA5-Land, NASA Earthdata, FIRMS):
see app/docs/data-api.md.

Source code and documentation: https://github.com/UrsaCrux/NasaSpace-Apps-2026
Licences: the program is Apache-2.0 (LICENSE); bundled third-party software
keeps its own licences (QGIS GPL-2.0+, Qt LGPL, WOFOST crop parameters
EUPL-1.2 in app/fieldshift/crops/wofost_parameters/).
