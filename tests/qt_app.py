"""One Qt application shared by every test module (only one may exist)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# field dialogs must not contact the data sources from the tests (tests that
# need loading pass their own fetch= function)
os.environ.setdefault("FIELDSHIFT_OFFLINE", "1")

from fieldshift.qt import HAS_QGIS, QtWidgets  # noqa: E402

_app = None


# ()
# the QgsApplication (or QApplication without QGIS), created on first call
def get_app():
    global _app
    if _app is None:
        if HAS_QGIS:
            import atexit
            from qgis.core import QgsApplication
            _app = QgsApplication([], False)
            _app.initQgis()
            # like the app does on close: without it QGIS can crash while the
            # interpreter exits (its OGR connection pool outlives GDAL)
            atexit.register(_app.exitQgis)
        else:
            _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return _app
