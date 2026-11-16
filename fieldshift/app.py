"""Application bootstrap: creates the Qt/QGIS application and the window."""

import argparse
import os
import sys
from pathlib import Path

from fieldshift import i18n
from fieldshift.qt import HAS_QGIS, QT_MAJOR, QtCore, QtGui, QtWidgets
from fieldshift.map import LayerSpec, create_map_view
from fieldshift.ui import MainWindow

# folder with the bundled datasets
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# offline country outlines, drawn below the tiles (visible without internet).
# base layers are "locked": the panel does not list them, so they cannot be removed
COUNTRIES = LayerSpec.vector("Countries", str(DATA_DIR / "countries.geojson"),
                             fill_color="#f2efe9", stroke_color="#9a8f80", locked=True)

# Sentinel-2 cloudless 2024 (EOX): 10 m satellite mosaic, no API key. free for
# non-commercial use under CC BY-NC-SA 4.0 as long as the credit below stays
# visible (https://cloudless.eox.at/documentation/license); a commercial
# product needs an agreement with EOX. tiles exist up to zoom 18. to change
# the basemap, change only this constant
DEFAULT_BASEMAP = LayerSpec.xyz(
    "Sentinel-2 cloudless 2024",
    "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg",
    zmin=0, zmax=18,
    locked=True,
    attribution="EOxCloudless https://cloudless.eox.at by EOX IT Services GmbH "
                "(Contains modified Copernicus Sentinel data 2024)",
)


# street map (roads, towns, names) the user can switch to from the map
# controls; hidden at start. OpenStreetMap requires the credit below
STREET_BASEMAP = LayerSpec.xyz(
    "OpenStreetMap",
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    locked=True,
    attribution="© OpenStreetMap contributors",
)


# (list argv)
# reads the command line: returns (str language or None, list of the
# arguments left for Qt). --lang must be one of i18n.available_languages();
# anything else makes the program print the usage and exit
def parse_args(argv):
    parser = argparse.ArgumentParser(prog="fieldshift", add_help=True)
    parser.add_argument("--lang", choices=i18n.available_languages(), metavar="CODE",
                        help="language of the texts: " + ", ".join(i18n.available_languages())
                        + f" (default: $FIELDSHIFT_LANG or {i18n.DEFAULT_LANGUAGE})")
    args, rest = parser.parse_known_args(argv[1:])
    return args.lang, [argv[0]] + rest


# (list argv)
# creates the QApplication (QgsApplication when QGIS is present), shows the
# main window and runs the event loop; returns the exit code. --lang CODE
# picks the language of the texts
def main(argv=None):
    argv = list(argv if argv is not None else sys.argv)
    lang, argv = parse_args(argv)
    if lang:
        i18n.set_language(lang)         # before any widget reads its texts
    app = _create_application(argv)
    force_light_theme(app)

    view = create_map_view()
    basemaps = {}
    for key, spec in (("countries", COUNTRIES), ("streets", STREET_BASEMAP),
                      ("satellite", DEFAULT_BASEMAP)):   # bottom layer first
        try:
            basemaps[key] = view.add_layer(spec)
        except ValueError as exc:
            print(f"warning: {exc}", file=sys.stderr)
    if "streets" in basemaps:
        view.set_layer_visible(basemaps["streets"], False)  # satellite first
    view.set_center(-70.64831, -33.45974, scale=400_000)  # Santiago, Chile

    window = MainWindow(view, basemaps={k: v for k, v in basemaps.items()
                                        if k in ("satellite", "streets")})
    window.show()
    code = app.exec()

    if HAS_QGIS:
        app.exitQgis()
    return code


# (QApplication app)
# forces the light look whatever the system theme is (dark desktops made
# the dark texts and white cards of the panels unreadable): Fusion style
# with its standard light palette, the same on Linux and Windows. Qt >= 6.8
# is also told the scheme is light, so native dialogs follow
def force_light_theme(app):
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(QtCore.Qt.ColorScheme.Light)
    style = QtWidgets.QStyleFactory.create("Fusion")
    if style is None:
        return
    app.setStyle(style)
    palette = style.standardPalette()
    # tooltips: dark text on pale yellow, like the classic light theme
    for group in (QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorGroup.Inactive):
        palette.setColor(group, QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor("#ffffdc"))
        palette.setColor(group, QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor("#000000"))
    app.setPalette(palette)


# (list argv)
# returns a QgsApplication initialised with the QGIS prefix path, or a plain
# QApplication when QGIS is not installed
def _create_application(argv):
    if not HAS_QGIS:
        return QtWidgets.QApplication(argv)

    from qgis.core import Qgis, QgsApplication

    if Qgis.versionInt() < 40000 or QT_MAJOR < 6:
        print(f"warning: Field Shift targets QGIS 4 / Qt6, found QGIS "
              f"{Qgis.version()} / Qt{QT_MAJOR}", file=sys.stderr)

    prefix = os.environ.get("QGIS_PREFIX_PATH")
    if prefix:
        QgsApplication.setPrefixPath(prefix, True)
    try:
        app = QgsApplication(argv, True)
    except TypeError:  # some builds want argv as bytes
        app = QgsApplication([a.encode() for a in argv], True)
    app.initQgis()
    return app
