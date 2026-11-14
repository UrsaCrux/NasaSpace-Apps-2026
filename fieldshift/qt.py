"""Qt import shim (Qt6).

QGIS 4 is built on Qt6 and ships its own PyQt6 build as ``qgis.PyQt``. When
QGIS cannot be imported we fall back to plain PyQt6, so the panel and window
can still be developed and run with the placeholder map. Always import Qt
classes from this module, and write enums fully scoped
(``Qt.AlignmentFlag.AlignCenter``, not ``Qt.AlignCenter``): PyQt6 requires it.
"""

import sys

# why QGIS could not be imported ("" when it was); shown by the placeholder map
QGIS_IMPORT_ERROR = ""

try:
    from qgis.PyQt import QtCore, QtGui, QtWidgets  # noqa: F401
    import qgis.core  # noqa: F401  (fails here if the bindings are broken)
    HAS_QGIS = True
except ImportError as exc:
    QGIS_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
    print(f"warning: cannot import QGIS ({QGIS_IMPORT_ERROR}) with "
          f"{sys.executable} (Python {sys.version.split()[0]}); "
          "see docs/README.md, 'QGIS is not found'", file=sys.stderr)
    from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: F401
    HAS_QGIS = False

# major Qt version actually loaded (6 expected)
QT_MAJOR = int(QtCore.qVersion().split(".")[0])
