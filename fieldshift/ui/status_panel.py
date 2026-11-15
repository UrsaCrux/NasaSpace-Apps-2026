"""Status panel: the right column of the map tab while "Status" is chosen,
with how one field is now. Top: field chooser and period (7 / 14 / 30 days
back). Below, scrolling: the "today" tiles, the warnings of the next 7 days,
then the Weather, Growth and Soil sections of the period (table left, chart
right, warnings under them). See fieldshift.ui.field_panel.
"""

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.status import PERIODS, status_report
from fieldshift.ui.analysis_widgets import format_date
from fieldshift.ui.field_panel import FieldPanel
from fieldshift.ui.status_widgets import SectionCard, SummaryTile, UpcomingCard


# the panel. open(layer_id) shows a field
class StatusPanel(FieldPanel):

    title_key = "modes.status"

    # (MapView view, FieldsManager fields, QWidget parent = None)
    def __init__(self, view, fields, parent=None):
        self.days = PERIODS[0]
        self.sections = {}             # section id -> SectionCard
        super().__init__(view, fields, parent)
        self.period_buttons = {}
        periods = QtWidgets.QHBoxLayout()
        periods.setSpacing(0)
        look_back = QtWidgets.QLabel(tr("status.look_back"))
        look_back.setStyleSheet("color: #555; margin-right: 4px;")
        periods.addWidget(look_back)
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
        self.sections = {}
        self.info_label.setText(tr("status.info", date=format_date(report.last_date)))
        today = QtWidgets.QLabel(
            f"<b>{tr('status.today')}</b> <span style='color:#666;'>· "
            f"{format_date(report.last_date)}</span>")
        today.setStyleSheet("font-size: 15px;")
        self.content_layout.addWidget(today)
        tiles = QtWidgets.QGridLayout()
        tiles.setSpacing(6)
        for i, tile in enumerate(report.summary):
            widget = SummaryTile(tile, report.days)
            widget.clicked.connect(self.show_row)
            tiles.addWidget(widget, i // 3, i % 3)
        holder = QtWidgets.QWidget()
        holder.setLayout(tiles)
        self.content_layout.addWidget(holder)
        # what comes: the short-forecast warnings of every section
        self.upcoming = UpcomingCard([a for a in report.alerts() if a.upcoming])
        self.upcoming.suggestion_requested.connect(
            lambda: self.suggestion_requested.emit(self.layer_id))
        self.content_layout.addWidget(self.upcoming)
        # what was observed: the last days, one card per section
        past = QtWidgets.QLabel(f"<b>{tr('status.past_title', days=report.days)}</b>")
        past.setStyleSheet("font-size: 15px; margin-top: 6px;")
        self.content_layout.addWidget(past)
        for section in report.sections:
            card = SectionCard(section, report.days)
            card.suggestion_requested.connect(
                lambda: self.suggestion_requested.emit(self.layer_id))
            self.content_layout.addWidget(card)
            self.sections[section.id] = card
        self.content_layout.addStretch(1)

    # (str section_id, str row_key)
    # scrolls to a section and shows that row in its chart
    def show_row(self, section_id, row_key):
        card = self.sections.get(section_id)
        if card is None or card.table is None:
            return
        card.table.select_key(row_key)
        QtCore.QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(card.y()))
