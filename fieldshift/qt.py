"""Qt import shim.

QGIS ships its own PyQt build (``qgis.PyQt``). When QGIS is not installed we
fall back to plain PyQt5, so the panel and window can still be developed and
run with the placeholder map. Always import Qt classes from this module.
"""

try:
    from qgis.PyQt import QtCore, QtGui, QtWidgets  # noqa: F401
    HAS_QGIS = True
except ImportError:
    from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: F401  # pyflakes: ignore
    HAS_QGIS = False
