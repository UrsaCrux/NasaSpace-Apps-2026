"""One Qt application shared by every test module (only one may exist)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift.qt import HAS_QGIS, QtWidgets  # noqa: E402

_app = None


# ()
# the QgsApplication (or QApplication without QGIS), created on first call
def get_app():
    global _app
    if _app is None:
        if HAS_QGIS:
            from qgis.core import QgsApplication
            _app = QgsApplication([], False)
            _app.initQgis()
        else:
            _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return _app
