"""Main window: map on the left, side panel on the right."""

from fieldshift import __version__
from fieldshift.analysis import get_analysis
from fieldshift.i18n import tr
from fieldshift.fields.manager import FieldsManager
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui.analysis_tab import AnalysisTab
from fieldshift.ui.analyze_dialog import AnalysisProgress, AnalyzeDialog
from fieldshift.ui.field_list import LAYER_ID_ROLE
from fieldshift.ui.fields_bar import FieldsBar
from fieldshift.ui.field_menu import FieldMenu
from fieldshift.ui.hover_card import HoverCard
from fieldshift.ui.map_controls import MapControls
from fieldshift.ui.scale_bar import ScaleBar
from fieldshift.ui.side_panel import SidePanel
from fieldshift.ui.weather_card import WeatherCard

# relative widths of the map and the panel inside the splitter
MAP_STRETCH = 3
PANEL_STRETCH = 1


# top-level window, made of tabs. The first tab ("Map", always there) holds
# the MapView with the FieldsBar under it (left) and the SidePanel (right),
# which share one FieldsManager. "Analyze…" adds one closable tab per
# analysis result
class MainWindow(QtWidgets.QMainWindow):

    # (MapView view, QWidget parent = None, dict basemaps = None)
    # builds the splitter layout around an already created map view.
    # basemaps maps "satellite" / "streets" to layer ids for the background switch
    def __init__(self, view, parent=None, basemaps=None):
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
        # scale bar over the bottom-left corner of the map
        self.scale_bar = ScaleBar(view)
        # zoom, "my fields" and background buttons over the top-left corner
        self.map_controls = MapControls(view, self.fields, basemaps)
        # card with the field under the mouse, and its outline highlighted
        self.hover_card = HoverCard(view, self.fields)
        # right click on a field: edit, analyze, zoom, check, delete
        self.field_menu = FieldMenu(self)
        # weather of the zone (now and 7 days) over the top-right corner
        self.weather_card = WeatherCard(view)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(map_area)
        splitter.addWidget(self.panel)
        splitter.setStretchFactor(0, MAP_STRETCH)
        splitter.setStretchFactor(1, PANEL_STRETCH)
        splitter.setCollapsible(0, False)
        splitter.setSizes([900, 300])

        # the map tab; analysis results open as more tabs next to it
        self.map_splitter = splitter
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.addTab(splitter, tr("tabs.map"))
        for side in (QtWidgets.QTabBar.ButtonPosition.LeftSide,
                     QtWidgets.QTabBar.ButtonPosition.RightSide):
            self.tabs.tabBar().setTabButton(0, side, None)       # the map cannot be closed
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.fields_bar.analyze_requested.connect(self.analyze)
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

    # (str layer_id = None)
    # asks for a field (layer_id first, if given) and analyses, runs them
    # with a progress window and opens one tab per result. returns the new
    # tabs (empty if cancelled)
    def analyze(self, layer_id=None):
        if self.fields.count() == 0 or self.view.is_drawing():
            return []
        dialog = AnalyzeDialog(self.fields, layer_id or self._field_to_preselect(), parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return []
        field = self.fields.field(dialog.layer_id())
        progress = AnalysisProgress(field, [get_analysis(i) for i in dialog.analysis_ids()],
                                    parent=self)
        if progress.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return []
        return self.open_results(field, progress.results())

    # (Field field, list results)
    # adds a tab for each AnalysisResult and shows the first one; returns the tabs
    def open_results(self, field, results):
        tabs = []
        for result in results:
            tab = AnalysisTab(result, field)
            index = self.tabs.addTab(tab, tab.tab_title())
            self.tabs.setTabToolTip(index, tr(tab.analysis.title_key))
            tabs.append(tab)
        if tabs:
            self.tabs.setCurrentWidget(tabs[0])
        return tabs

    # the field the Analyze dialog starts with: the first checked one, else
    # the highlighted row, else none (the dialog picks the first)
    def _field_to_preselect(self):
        checked = self.fields.selected()
        if checked:
            return checked[0]
        item = self.panel.layer_list.currentItem()
        return item.data(LAYER_ID_ROLE) if item is not None else None

    def _close_tab(self, index):
        if index > 0:                            # never the map
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            widget.deleteLater()

    # shows the "attribution" of every visible layer, once each
    def _show_attribution(self):
        credits = []
        for info in self.view.layers():
            if info.visible and info.attribution and info.attribution not in credits:
                credits.append(info.attribution)
        self.attribution_label.setText(" · ".join(credits))

    def _show_cursor(self, lon, lat):
        self.statusBar().showMessage(tr("status.cursor", lon=f"{lon:.5f}", lat=f"{lat:.5f}"))
