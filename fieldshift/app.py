"""Application bootstrap: creates the Qt/QGIS application and the window."""

import argparse
import os
import sys
from pathlib import Path

from fieldshift import i18n
from fieldshift.qt import HAS_QGIS, QT_MAJOR, QtWidgets
from fieldshift.map import LayerSpec, create_map_view
from fieldshift.ui import MainWindow

# folder with the bundled datasets
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# offline country outlines, drawn below the tiles (visible without internet).
# base layers are "locked": the panel does not list them, so they cannot be removed
COUNTRIES = LayerSpec.vector("Countries", str(DATA_DIR / "countries.geojson"),
                             fill_color="#f2efe9", stroke_color="#9a8f80", locked=True)

# OpenStreetMap tile layer loaded at start-up
DEFAULT_BASEMAP = LayerSpec.xyz(
    "OpenStreetMap",
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    locked=True,
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

    view = create_map_view()
    for spec in (COUNTRIES, DEFAULT_BASEMAP):   # bottom layer first
        try:
            view.add_layer(spec)
        except ValueError as exc:
            print(f"warning: {exc}", file=sys.stderr)
    view.set_center(-70.64831, -33.45974, scale=400_000)  # Santiago, Chile

    window = MainWindow(view)
    window.show()
    code = app.exec()

    if HAS_QGIS:
        app.exitQgis()
    return code


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
