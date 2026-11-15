"""Status panel: the right column of the map tab while "Status" is chosen,
with how one field is now. Top: field chooser and period (7 / 14 / 30 days).
Below, scrolling: the "today" tiles, then the Weather, Growth and Soil
sections (table left, chart right, alerts under them).

Clicking another field on the map shows that field; choosing one in the
list also moves the map to it. Uses the map only
through MapView (clicked, layer_hovered) and the fields through
FieldsManager. Every text comes from fieldshift/i18n/<language>.json.
"""

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.status import PERIODS, status_report
from fieldshift.ui.analysis_widgets import format_date
from fieldshift.ui.status_widgets import SectionCard, SummaryTile

# smallest width of the panel (pixels)
MIN_WIDTH_PX = 520

_STYLE = """
QFrame#statusPanel { background: #f4f6f4; }
QScrollArea, QWidget#statusContent { background: transparent; border: none; }
QPushButton#period { border: 1px solid #9aa39a; padding: 3px 10px; background: white; }
QPushButton#period:checked { background: #00796b; color: white; border-color: #00796b; }
QLabel#exampleBanner { background: #fff8e1; border: 1px solid #ffe082; border-radius: 4px;
                       padding: 4px 8px; color: #6d4c00; }
"""


# the panel. open(layer_id) shows a field
class StatusPanel(QtWidgets.QFrame):

    # (MapView view, FieldsManager fields, QWidget parent = None)
    def __init__(self, view, fields, parent=None):
        super().__init__(parent)
        self.view = view
        self.fields = fields
        self.layer_id = None           # field shown
        self.days = PERIODS[0]
        self.report = None             # StatusReport shown
        self.sections = {}             # section id -> SectionCard
        self._hovered = None           # field under the mouse on the map
        # emitted with (str layer_id) when an alert's "See suggestion" is clicked
        self.suggestion_requested = Event()
        self.setObjectName("statusPanel")
        self.setStyleSheet(_STYLE)

        title = QtWidgets.QLabel(f"<b>{tr('modes.status')}</b>")
        title.setStyleSheet("font-size: 17px;")
        self.field_box = QtWidgets.QComboBox()
        self.field_box.setMinimumWidth(160)
        self.field_box.setToolTip(tr("status.field_tooltip"))
        self.field_box.activated.connect(self._on_field_chosen)
        self.period_buttons = {}
        periods = QtWidgets.QHBoxLayout()
        periods.setSpacing(0)
        group = QtWidgets.QButtonGroup(self)
        for days in PERIODS:
            button = QtWidgets.QPushButton(tr("status.days", days=days))
            button.setObjectName("period")
            button.setCheckable(True)
            button.setChecked(days == self.days)
            button.setToolTip(tr("status.period_tooltip"))
            button.clicked.connect(lambda _=False, d=days: self.set_days(d))
            group.addButton(button)
            periods.addWidget(button)
            self.period_buttons[days] = button
        header = QtWidgets.QHBoxLayout()
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self.field_box, 1)
        header.addSpacing(8)
        header.addLayout(periods)

        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("color: #666; font-size: 11px;")
        self.example_label = QtWidgets.QLabel(tr("status.example"))
        self.example_label.setObjectName("exampleBanner")
        self.example_label.setWordWrap(True)

        self.content = QtWidgets.QWidget()
        self.content.setObjectName("statusContent")
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(10)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidget(self.content)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 8, 10)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.info_label)
        layout.addWidget(self.example_label)
        layout.addWidget(self.scroll, 1)
        self.setMinimumWidth(MIN_WIDTH_PX)

        view.layer_hovered.connect(self._on_hover)
        view.clicked.connect(self._on_map_click)
        fields.fields_changed.connect(self._on_fields_changed)

    # (str layer_id)
    # shows that field (the first one when None). returns True when a field
    # is shown
    def open(self, layer_id=None):
        ids = self.fields.layer_ids()
        if not ids:
            return False
        self.layer_id = layer_id if layer_id in ids else ids[0]
        self._fill_fields()
        self.refresh()
        return True

    # (int days)
    # shows the last days (one of PERIODS)
    def set_days(self, days):
        self.days = days
        self.period_buttons[days].setChecked(True)
        if self.report is not None:
            self.refresh()

    # ()
    # builds the report of the field and period shown again
    def refresh(self):
        field = self.fields.field(self.layer_id)
        if field is None:
            return
        self.report = report = status_report(field, self.days)
        self.info_label.setText(tr("status.info", date=format_date(report.last_date),
                                   days=report.days))
        self.example_label.setVisible(report.example)
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.sections = {}

        today = QtWidgets.QLabel(f"<b>{tr('status.today')}</b>")
        self.content_layout.addWidget(today)
        tiles = QtWidgets.QGridLayout()
        tiles.setSpacing(6)
        for i, tile in enumerate(report.summary):
            widget = SummaryTile(tile)
            widget.clicked.connect(self.show_row)
            tiles.addWidget(widget, i // 3, i % 3)
        alerts = len(report.alerts())
        holder = QtWidgets.QWidget()
        holder.setLayout(tiles)
        self.content_layout.addWidget(holder)
        if alerts:
            count = QtWidgets.QLabel(tr("status.alert_count", count=alerts))
            count.setStyleSheet("color: #c62828;")
            self.content_layout.addWidget(count)
        for section in report.sections:
            card = SectionCard(section)
            card.suggestion_requested.connect(
                lambda: self.suggestion_requested.emit(self.layer_id))
            self.content_layout.addWidget(card)
            self.sections[section.id] = card
        self.content_layout.addStretch(1)

    # (str section_id, str row_key)
    # scrolls to a section and shows that row in its chart
    def show_row(self, section_id, row_key):
        card = self.sections.get(section_id)
        if card is None:
            return
        card.table.select_key(row_key)
        QtCore.QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(card.y()))

    # -- helpers -----------------------------------------------------------

    def _fill_fields(self):
        self.field_box.blockSignals(True)
        self.field_box.clear()
        for layer_id in self.fields.layer_ids():
            self.field_box.addItem(self.fields.field(layer_id).name, layer_id)
        self.field_box.setCurrentIndex(max(0, self.field_box.findData(self.layer_id)))
        self.field_box.blockSignals(False)

    def _on_field_chosen(self, index):
        layer_id = self.field_box.itemData(index)
        self.open(layer_id)
        self.fields.zoom_to(layer_id)

    def _on_hover(self, layer_id, lon, lat):
        self._hovered = layer_id if self.fields.is_field(layer_id) else None

    def _on_map_click(self, lon, lat):
        if self.isVisible() and self._hovered and self._hovered != self.layer_id:
            self.open(self._hovered)

    def _on_fields_changed(self):
        if not self.isVisible():
            return
        if self.fields.is_field(self.layer_id):
            self._fill_fields()
        else:
            self.open(None)            # the field shown was deleted
