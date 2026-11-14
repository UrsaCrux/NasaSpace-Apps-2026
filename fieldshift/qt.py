"""Qt import shim (Qt6).

QGIS 4 is built on Qt6 and ships its own PyQt6 build as ``qgis.PyQt``. When
QGIS is not installed we fall back to plain PyQt6, so the panel and window
can still be developed and run with the placeholder map. Always import Qt
classes from this module, and write enums fully scoped
(``Qt.AlignmentFlag.AlignCenter``, not ``Qt.AlignCenter``): PyQt6 requires it.
"""

try:
    from qgis.PyQt import QtCore, QtGui, QtWidgets  # noqa: F401
    HAS_QGIS = True
except ImportError:
    from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: F401
    HAS_QGIS = False

# major Qt version actually loaded (6 expected)
QT_MAJOR = int(QtCore.qVersion().split(".")[0])
