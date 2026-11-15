"""Status panel: the right column of the map tab while "Status" is chosen,
with how one field is now. Top: field chooser and period (7 / 14 / 30 days).
Below: the "today" tiles (newest value of each datum and its trend against
the period mean). See fieldshift.ui.field_panel (field chooser, map clicks,
loading in the background).
"""

from fieldshift.i18n import tr
from fieldshift.qt import QtWidgets
from fieldshift.status import PERIODS, status_report
from fieldshift.ui.analysis_widgets import format_date
from fieldshift.ui.field_panel import FieldPanel
from fieldshift.ui.status_widgets import SummaryTile


# the panel. open(layer_id) shows a field
class StatusPanel(FieldPanel):

    title_key = "modes.status"

    # (MapView view, FieldsManager fields, QWidget parent = None)
    def __init__(self, view, fields, parent=None):
        self.days = PERIODS[0]
        self.tiles = []                # SummaryTile widgets shown
        super().__init__(view, fields, parent)
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
        self.header.addSpacing(8)
        self.header.addLayout(periods)

    # (int days)
    # shows the last days (one of PERIODS)
    def set_days(self, days):
        self.days = days
        self.period_buttons[days].setChecked(True)
        if self.layer_id is not None:
            self.refresh()

    def make_report(self, field):
        return status_report(field, self.days)

    def build(self, report):
        self.info_label.setText(tr("status.info", date=format_date(report.last_date)))
        today = QtWidgets.QLabel(f"<b>{tr('status.today')}</b>")
        self.content_layout.addWidget(today)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        self.tiles = []
        for i, tile in enumerate(report.summary):
            widget = SummaryTile(tile, report.days)
            grid.addWidget(widget, i // 3, i % 3)
            self.tiles.append(widget)
        holder = QtWidgets.QWidget()
        holder.setLayout(grid)
        self.content_layout.addWidget(holder)
        self.content_layout.addStretch(1)
