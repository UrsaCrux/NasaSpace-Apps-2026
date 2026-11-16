"""Status panel: the right column of the map tab while "Status" is chosen,
with how one field is today and in the coming days. Scrolling: today's
tiles, "Coming days" (7 / 14 days: chart, day slider, light warnings, link to
Analyze) and the crop follow-up (NDVI, loaded apart because MODIS is slow).
The past is in Trends. See fieldshift.ui.field_panel.
"""

import os
import threading

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.status import HORIZONS, crop_tracking, status_report
from fieldshift.status.progress import crop_progress
from fieldshift.ui.analysis_widgets import format_date
from fieldshift.ui.field_panel import OFFLINE_ENV, FieldPanel
from fieldshift.ui.status_widgets import ForecastCard, TodayTile, TrackingCard

# tiles per row
TILE_COLUMNS = 4


# the panel. open(layer_id) shows a field
class StatusPanel(FieldPanel):

    title_key = "modes.status"

    # internal: (int request number, Tracking or None, Exception or None)
    _tracked = QtCore.pyqtSignal(int, object, object)

    # (MapView view, FieldsManager fields, QWidget parent = None)
    def __init__(self, view, fields, parent=None):
        self.horizon = HORIZONS[0]
        self.tiles = []                # TodayTile widgets shown
        self.forecast_card = None
        self.tracking_card = None
        super().__init__(view, fields, parent)
        self._tracked.connect(self._on_tracked)
        fields.records_changed.connect(self._on_records_changed)

    def make_report(self, field):
        return status_report(field)

    def build(self, report):
        day = report.forecast.days[0]
        self.info_label.setText(f"<b>{report.field_name}</b> · " + tr(
            "status.info_today", date=format_date(day.date),
            time=report.forecast.now[11:16] or "—"))
        today = QtWidgets.QLabel(f"<b>{tr('status.today')}</b>")
        today.setStyleSheet("font-size: 15px;")
        self.content_layout.addWidget(today)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        self.tiles = []
        for i, tile in enumerate(report.tiles):
            widget = TodayTile(tile)
            grid.addWidget(widget, i // TILE_COLUMNS, i % TILE_COLUMNS)
            self.tiles.append(widget)
        holder = QtWidgets.QWidget()
        holder.setLayout(grid)
        self.content_layout.addWidget(holder)

        self.forecast_card = ForecastCard(report, self.horizon)
        for days, button in self.forecast_card.horizon_buttons.items():
            button.clicked.connect(lambda _=False, d=days: setattr(self, "horizon", d))
        self.forecast_card.analyze_requested.connect(
            lambda: self.suggestion_requested.emit(self.layer_id))
        self.content_layout.addWidget(self.forecast_card)

        self.tracking_card = TrackingCard()
        self.tracking_card.retry_requested.connect(self._start_tracking)
        self.tracking_card.records_requested.connect(self.open_records)
        field = self.fields.field(self.layer_id)
        self.tracking_card.set_progress(crop_progress(field.records if field else ()))
        self.content_layout.addWidget(self.tracking_card)
        self.content_layout.addStretch(1)
        self._start_tracking()

    def _start_tracking(self):
        field, request = self.fields.field(self.layer_id), self._request
        if field is None:
            return
        self.tracking_card.text.setText(tr("status.tracking_loading"))
        self.tracking_card.retry_button.hide()

        def run():
            try:
                self._tracked.emit(request, crop_tracking(field), None)
            except Exception as exc:
                self._tracked.emit(request, None, exc)
        if os.environ.get(OFFLINE_ENV) == "1":
            run()
            return
        threading.Thread(target=run, daemon=True, name="status-tracking").start()

    # ()
    # opens the measurements window of the field shown
    def open_records(self):
        from fieldshift.ui.records_dialog import RecordsDialog
        if self.fields.field(self.layer_id) is not None:
            RecordsDialog(self.fields, self.layer_id, self).exec()

    def _on_records_changed(self, layer_id):
        if layer_id == self.layer_id and self.report is not None:
            self.refresh()                # measurements change tiles and follow-up

    def _on_tracked(self, request, tracking, error):
        if request == self._request and self.tracking_card is not None:
            self.tracking_card.set_tracking(tracking, error)
