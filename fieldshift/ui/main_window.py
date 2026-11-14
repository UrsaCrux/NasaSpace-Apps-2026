"""Main window: map on the left, side panel on the right."""

from fieldshift import __version__
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui.side_panel import SidePanel

# relative widths of the map and the panel inside the splitter
MAP_STRETCH = 3
PANEL_STRETCH = 1


# top-level window. Owns a MapView (left) and a SidePanel (right)
class MainWindow(QtWidgets.QMainWindow):

    # (MapView view, QWidget parent = None)
    # builds the splitter layout around an already created map view
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.panel = SidePanel(view)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(view.widget())
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, MAP_STRETCH)
        splitter.setStretchFactor(1, PANEL_STRETCH)
        splitter.setCollapsible(0, False)
        splitter.setSizes([900, 300])

        self.setCentralWidget(splitter)
        self.setWindowTitle(f"Field Shift {__version__}")
        self.resize(1280, 800)
        self.statusBar().showMessage("Ready")
        view.cursor_moved.connect(self._show_cursor)

    def _show_cursor(self, lon, lat):
        self.statusBar().showMessage(f"lon {lon:.5f}   lat {lat:.5f}")
