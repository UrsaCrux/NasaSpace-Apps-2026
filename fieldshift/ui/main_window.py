"""Main window: map on the left, side panel on the right."""

from fieldshift import __version__
from fieldshift.i18n import tr
from fieldshift.fields.manager import FieldsManager
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui.fields_bar import FieldsBar
from fieldshift.ui.side_panel import SidePanel

# relative widths of the map and the panel inside the splitter
MAP_STRETCH = 3
PANEL_STRETCH = 1


# top-level window. Owns a MapView with the FieldsBar under it (left) and a
# SidePanel (right); both share one FieldsManager
class MainWindow(QtWidgets.QMainWindow):

    # (MapView view, QWidget parent = None)
    # builds the splitter layout around an already created map view
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.fields = FieldsManager(view)
        self.panel = SidePanel(view, fields=self.fields)
        self.fields_bar = FieldsBar(view, self.fields)

        map_area = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(map_area)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(view.widget(), 1)
        column.addWidget(self.fields_bar)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(map_area)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, MAP_STRETCH)
        splitter.setStretchFactor(1, PANEL_STRETCH)
        splitter.setCollapsible(0, False)
        splitter.setSizes([900, 300])

        self.setCentralWidget(splitter)
        self.setWindowTitle(f"Field Shift {__version__}")
        self.resize(1280, 800)
        self.statusBar().showMessage(tr("status.ready"))
        # credit of the visible layers (basemap licences require it)
        self.attribution_label = QtWidgets.QLabel()
        self.attribution_label.setStyleSheet("color: #444; padding-right: 6px;")
        self.statusBar().addPermanentWidget(self.attribution_label)
        view.layers_changed.connect(self._show_attribution)
        self._show_attribution()
        view.cursor_moved.connect(self._show_cursor)

    # shows the "attribution" of every visible layer, once each
    def _show_attribution(self):
        credits = []
        for info in self.view.layers():
            if info.visible and info.attribution and info.attribution not in credits:
                credits.append(info.attribution)
        self.attribution_label.setText(" · ".join(credits))

    def _show_cursor(self, lon, lat):
        self.statusBar().showMessage(tr("status.cursor", lon=f"{lon:.5f}", lat=f"{lat:.5f}"))
