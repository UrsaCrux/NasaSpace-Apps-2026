"""Pieces of the Status panel: today's tiles, the coming days (a chart per
variable with a day slider, the chosen day's details and light warnings)
and the crop follow-up. Pure Qt, no QGIS.
"""

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.status import HORIZONS, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH

# colour of each level
LEVEL_COLORS = {LEVEL_OK: "#2e7d32", LEVEL_WATCH: "#ef8f00", LEVEL_ALERT: "#d65858"}
# chart colours
_LINE = QtGui.QColor("#2e7d32")
_BARS = QtGui.QColor("#1e88e5")
_MEAN = QtGui.QColor("#9e9e9e")
_GRID = QtGui.QColor("#e3e6e3")
_INK = QtGui.QColor("#333333")
_LINK = ("QPushButton { color: #1565c0; border: none; text-align: left; }"
         " QPushButton:hover { text-decoration: underline; }")


# (str iso_date)
# short date: "8 Nov" / "8 nov"
def short_date(iso_date):
    return f"{int(iso_date[8:10])} {tr(f'month_short.{int(iso_date[5:7])}')}"


# (str source)
# a source name, translated when it is an i18n key ("status.source.farmer")
def source_text(source):
    return tr(source) if source.startswith("status.") else source


# a tile of today: icon, name, value and a short note
class TodayTile(QtWidgets.QFrame):

    # (status.TodayTile tile)
    def __init__(self, tile, parent=None):
        super().__init__(parent)
        self.tile = tile
        color = LEVEL_COLORS.get(tile.level, LEVEL_COLORS[LEVEL_OK])
        self.setObjectName("summaryTile")
        self.setStyleSheet(
            f"QFrame#summaryTile {{ background: white; border: 1px solid #d5dbd5;"
            f" border-left: 4px solid {color}; border-radius: 6px; }}"
            f" QFrame#summaryTile:hover {{ background: #f1f8f1; }}"
            f" QLabel {{ border: none; background: transparent; }}")
        name = QtWidgets.QLabel(tr(tile.label_key))
        name.setStyleSheet("color: #555; font-size: 11px;")
        if tile.value is None:
            text = "—"
        else:
            text = f"{tile.value:.{tile.decimals}f}" + (f" {tile.unit}" if tile.unit else "")
        self.value_label = QtWidgets.QLabel(f"<b>{text}</b>")
        self.value_label.setStyleSheet("font-size: 16px; color: #1b1b1b;")
        note = QtWidgets.QLabel(tr(tile.note_key, **tile.note_params) if tile.note_key else "")
        note.setStyleSheet(f"color: {color if tile.level != LEVEL_OK else '#666'};"
                           " font-size: 11px;")
        note.setWordWrap(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        for label in (name, self.value_label, note):
            layout.addWidget(label)


# variables of the forecast chart: key, i18n label, unit, decimals
FORECAST_VARIABLES = (("temp", "status.fc.temp", "°C", 0),
                      ("rain", "status.fc.rain", "mm", 1),
                      ("wind", "status.fc.wind", "km/h", 0),
                      ("humidity", "status.fc.humidity", "%", 0),
                      ("radiation", "status.fc.radiation", "MJ/m²", 1))
_HOT = QtGui.QColor("#e53935")
_COLD = QtGui.QColor("#1e88e5")


# (int index, str iso_date)
# "Today" / "Tomorrow" / "Mon 17" for the day number index of the forecast
def day_label(index, iso_date):
    if index == 0:
        return tr("status.day.today")
    if index == 1:
        return tr("status.when.tomorrow")
    from fieldshift.ui.weather_card import weekday_name
    return f"{weekday_name(iso_date)} {int(iso_date[8:10])}"


# (DayForecast day, str variable)
# (main value, second value or None) of a day for a FORECAST_VARIABLES key
def day_values(day, variable):
    if variable == "temp":
        return day.tmax, day.tmin
    return {"rain": day.rain_mm, "wind": day.wind_kmh, "humidity": day.humidity,
            "radiation": day.radiation}[variable], None


# chart of the next 7 days for one variable (temperature: max and min),
# with the chosen day marked. click a day to choose it
class ForecastChart(QtWidgets.QWidget):

    # (tuple days)
    def __init__(self, days, parent=None):
        super().__init__(parent)
        self.days = days
        self.variable = "temp"
        self.selected = 0
        # emitted with (int index) when the user clicks a day
        self.day_clicked = Event()
        self.setMinimumSize(300, 170)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    # (str variable, int selected, tuple days = None)
    # draws a variable with the day number selected marked (and other days)
    def show_day(self, variable, selected, days=None):
        if days is not None:
            self.days = days
        self.variable, self.selected = variable, selected
        self.update()

    def _plot(self):
        metrics = self.fontMetrics()
        return QtCore.QRectF(40, metrics.height() + 6, self.width() - 50,
                             self.height() - 2 * metrics.height() - 14)

    def _x(self, plot, i):
        return plot.left() + plot.width() * (i + 0.5) / len(self.days)

    def mousePressEvent(self, event):
        plot = self._plot()
        x = event.position().x()
        self.day_clicked.emit(min(range(len(self.days)), key=lambda i: abs(self._x(plot, i) - x)))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        metrics, plot = self.fontMetrics(), self._plot()
        pairs = [day_values(d, self.variable) for d in self.days]
        known = [v for pair in pairs for v in pair if v is not None]
        if not known:
            painter.setPen(_MEAN)
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter,
                             tr("status.no_data"))
            return
        bars = self.variable == "rain"
        low, high = (0.0 if bars else min(known)), max(known)
        if high - low < 1:
            high = low + 1
        pad = (high - low) * 0.15
        low, high = (low if bars else low - pad), high + pad

        def y(v):
            return plot.bottom() - plot.height() * (v - low) / (high - low)

        # chosen day band
        width = plot.width() / len(self.days)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(249, 168, 37, 50))
        painter.drawRect(QtCore.QRectF(self._x(plot, self.selected) - width / 2, plot.top(),
                                       width, plot.height()))
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(plot)
        painter.setPen(_INK)
        for v in (low, high):
            painter.drawText(QtCore.QRectF(0, y(v) - metrics.height() / 2, plot.left() - 6,
                                           metrics.height()),
                             QtCore.Qt.AlignmentFlag.AlignRight
                             | QtCore.Qt.AlignmentFlag.AlignVCenter, f"{v:.0f}")
        step = max(1, round(len(self.days) * (metrics.horizontalAdvance("Mmm 00") + 6)
                            / max(1.0, plot.width())))
        for i, day in enumerate(self.days):
            if i % step and i != self.selected:
                continue
            text = day_label(i, day.date)
            font = painter.font()
            font.setBold(i == self.selected)
            painter.setFont(font)
            painter.drawText(QtCore.QPointF(self._x(plot, i) - metrics.horizontalAdvance(text) / 2,
                                            self.height() - 4), text)
        font = painter.font()
        font.setBold(False)
        painter.setFont(font)

        if bars:
            for i, (v, _) in enumerate(pairs):
                if v is None:
                    continue
                color = QtGui.QColor(_BARS)
                if i != self.selected:
                    color.setAlpha(150)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(QtCore.QRectF(self._x(plot, i) - width * 0.3, y(v), width * 0.6,
                                               plot.bottom() - y(v)))
                chance = self.days[i].rain_chance
                if chance is not None and len(self.days) <= 7:
                    painter.setPen(_MEAN)
                    label = f"{chance:.0f}%"
                    painter.drawText(QtCore.QPointF(
                        self._x(plot, i) - metrics.horizontalAdvance(label) / 2,
                        y(v) - 3), label)
        else:
            lines = [(0, _HOT if self.variable == "temp" else _LINE)]
            if self.variable == "temp":
                lines.append((1, _COLD))
            for slot, color in lines:
                points = [(i, p[slot]) for i, p in enumerate(pairs) if p[slot] is not None]
                painter.setPen(QtGui.QPen(color, 2.2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                for (i0, v0), (i1, v1) in zip(points, points[1:]):
                    painter.drawLine(QtCore.QPointF(self._x(plot, i0), y(v0)),
                                     QtCore.QPointF(self._x(plot, i1), y(v1)))
                for i, v in points:
                    painter.setBrush(color if i == self.selected else QtGui.QColor("white"))
                    painter.drawEllipse(QtCore.QPointF(self._x(plot, i), y(v)), 4, 4)
                    if i == self.selected:
                        painter.drawText(QtCore.QPointF(self._x(plot, i) + 6, y(v) - 6),
                                         f"{v:.0f}")
        painter.end()


# the next 7 days: a chart of the chosen variable, a slider (and play button)
# to move through the days, the details of the chosen day, and the warnings

# the coming days: how many (7 / 14), a chart of the chosen variable, a
# slider (and play button) through the days, the chosen day's details, the
# light warnings and a link to Analyze for more
class ForecastCard(QtWidgets.QFrame):

    # (StatusReport report, int horizon = HORIZONS[0])
    def __init__(self, report, horizon=HORIZONS[0], parent=None):
        super().__init__(parent)
        self.report = report
        self.all_days = tuple(report.forecast.days)
        self.horizon = horizon
        self.variable = "temp"
        # emitted with no arguments when "More in Analyze" is clicked
        self.analyze_requested = Event()
        self.setObjectName("forecastCard")
        self.setStyleSheet("QFrame#forecastCard { background: white; border: 1px solid #d5dbd5;"
                           " border-radius: 8px; } QLabel { background: transparent;"
                           " border: none; }"
                           " QPushButton#fcVar, QPushButton#horizon { background: white;"
                           " border: 1px solid #c9d1c9; padding: 3px 10px; }"
                           " QPushButton#fcVar:checked, QPushButton#horizon:checked"
                           " { background: #00796b; color: white; border-color: #00796b; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"<b>{tr('status.soon_title')}</b>")
        title.setStyleSheet("font-size: 15px;")
        top.addWidget(title, 1)
        self.horizon_buttons = {}
        group = QtWidgets.QButtonGroup(self)
        for days in HORIZONS:
            button = QtWidgets.QPushButton(tr("status.days", days=days))
            button.setObjectName("horizon")
            button.setCheckable(True)
            button.setChecked(days == horizon)
            button.setToolTip(tr("status.horizon_tooltip", max=len(self.all_days)))
            button.clicked.connect(lambda _=False, d=days: self.set_horizon(d))
            group.addButton(button)
            top.addWidget(button)
            self.horizon_buttons[days] = button
        layout.addLayout(top)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(0)
        group = QtWidgets.QButtonGroup(self)
        self.variable_buttons = {}
        for key, label, _, _ in FORECAST_VARIABLES:
            button = QtWidgets.QPushButton(tr(label))
            button.setObjectName("fcVar")
            button.setCheckable(True)
            button.setChecked(key == self.variable)
            button.clicked.connect(lambda _=False, k=key: self.set_variable(k))
            group.addButton(button)
            buttons.addWidget(button)
            self.variable_buttons[key] = button
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.chart = ForecastChart(self.days())
        self.chart.day_clicked.connect(lambda i: self.slider.setValue(i))
        layout.addWidget(self.chart)
        controls = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("▶")
        self.play_button.setFixedWidth(34)
        self.play_button.setToolTip(tr("status.fc.play"))
        self.play_button.clicked.connect(self.toggle_play)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.setToolTip(tr("status.fc.slider"))
        self.slider.valueChanged.connect(self.show_day)
        controls.addWidget(self.play_button)
        controls.addWidget(self.slider, 1)
        layout.addLayout(controls)
        self.detail = QtWidgets.QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("QLabel { background: #f6f8f6; border: 1px solid #e0e5e0;"
                                  " border-radius: 6px; padding: 6px 8px; }")
        layout.addWidget(self.detail)

        heading = QtWidgets.QLabel(f"<b>{tr('status.tips_title')}</b>")
        layout.addWidget(heading)
        self.alerts_box = QtWidgets.QVBoxLayout()
        self.alerts_box.setSpacing(3)
        layout.addLayout(self.alerts_box)
        more = QtWidgets.QPushButton(tr("status.more_in_analyze"))
        more.setFlat(True)
        more.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        more.setStyleSheet(_LINK)
        more.clicked.connect(lambda: self.analyze_requested.emit())
        layout.addWidget(more)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self._step)
        self.set_horizon(horizon)

    # ()
    # the days shown (today first)
    def days(self):
        return self.all_days[:self.horizon]

    # (int days)
    # shows the next days (one of HORIZONS)
    def set_horizon(self, days):
        self.horizon = days
        self.horizon_buttons[days].setChecked(True)
        self.slider.blockSignals(True)
        self.slider.setRange(0, len(self.days()) - 1)
        self.slider.setValue(min(self.slider.value(), len(self.days()) - 1))
        self.slider.blockSignals(False)
        self._fill_alerts()
        self.show_day(self.slider.value())

    # (str variable)
    # draws another FORECAST_VARIABLES key in the chart
    def set_variable(self, variable):
        self.variable = variable
        self.variable_buttons[variable].setChecked(True)
        self.chart.show_day(variable, self.slider.value(), self.days())

    # (int index)
    # marks the day number index and shows its details
    def show_day(self, index):
        day = self.days()[index]
        self.chart.show_day(self.variable, index, self.days())

        def part(key, value, decimals, unit):
            return None if value is None else tr(key, value=f"{value:.{decimals}f}", unit=unit)
        rain = tr("status.fc.d_rain", value=f"{day.rain_mm:.1f}")
        if day.rain_chance is not None:
            rain += f" ({day.rain_chance:.0f}%)"
        parts = [tr("status.fc.d_temp", tmax=f"{day.tmax:.0f}", tmin=f"{day.tmin:.0f}"), rain,
                 part("status.fc.d_wind", day.wind_kmh, 0, "km/h"),
                 part("status.fc.d_humidity", day.humidity, 0, "%"),
                 part("status.fc.d_radiation", day.radiation, 1, "MJ/m²")]
        text = (f"<b>{day_label(index, day.date)}</b> · {short_date(day.date)}<br>"
                + " · ".join(p for p in parts if p))
        for alert in self.report.alerts:
            if alert.date == day.date:
                color = LEVEL_COLORS.get(alert.level, LEVEL_COLORS[LEVEL_WATCH])
                text += (f"<br><span style='color:{color}'>"
                         f"{tr(alert.text_key, **alert.params)}</span>")
        self.detail.setText(text)

    # ()
    # starts or stops moving through the days by itself
    def toggle_play(self):
        if self._timer.isActive():
            self._timer.stop()
            self.play_button.setText("▶")
            return
        if self.slider.value() == self.slider.maximum():
            self.slider.setValue(0)
        self._timer.start()
        self.play_button.setText("⏸")

    def _step(self):
        if self.slider.value() >= self.slider.maximum():
            self.toggle_play()
            return
        self.slider.setValue(self.slider.value() + 1)

    def _fill_alerts(self):
        while self.alerts_box.count():
            item = self.alerts_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        days = self.days()
        index = {d.date: i for i, d in enumerate(days)}
        alerts = self.report.alerts_within(len(days))
        self.alert_labels = []
        for alert in alerts:
            color = LEVEL_COLORS.get(alert.level, LEVEL_COLORS[LEVEL_WATCH])
            when = day_label(index[alert.date], alert.date)
            label = QtWidgets.QLabel(
                f"<span style='color:{color}'>●</span> <b>{when}</b>: "
                f"{tr(alert.text_key, **alert.params)}")
            label.setWordWrap(True)
            self.alerts_box.addWidget(label)
            self.alert_labels.append(label)
        if not alerts:
            label = QtWidgets.QLabel(tr("status.no_tips", days=len(days)))
            label.setStyleSheet("color: #555;")
            self.alerts_box.addWidget(label)


# the crop follow-up: crop name, newest NDVI and its change against the
# image before. starts "loading"; set_tracking() fills it
class TrackingCard(QtWidgets.QFrame):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("trackingCard")
        self.setStyleSheet("QFrame#trackingCard { background: white; border: 1px solid #d5dbd5;"
                           " border-radius: 8px; }"
                           " QLabel { border: none; background: transparent; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        title = QtWidgets.QLabel(f"<b>{tr('status.tracking_title')}</b>")
        title.setStyleSheet("font-size: 15px;")
        self.text = QtWidgets.QLabel(tr("status.tracking_loading"))
        self.text.setWordWrap(True)
        self.text.setStyleSheet("color: #555;")
        layout.addWidget(title)
        layout.addWidget(self.text)

    # (Tracking tracking or None, bool failed = False)
    def set_tracking(self, tracking, failed=False):
        if tracking is None:
            self.text.setText(tr("status.tracking_failed" if failed else "status.tracking_none"))
            return
        crop = tracking.crop or tr("status.tracking_no_crop")
        lines = [tr("status.tracking_ndvi", crop=crop, ndvi=f"{tracking.ndvi:.2f}",
                    date=short_date(tracking.date))]
        change = tracking.change_pct()
        if change is not None:
            color = "#2e7d32" if change >= 0 else LEVEL_COLORS[LEVEL_WATCH]
            lines.append(f"<span style='color:{color}'><b>{change:+.0f}%</b></span> "
                         + tr("status.tracking_change", date=short_date(tracking.previous_date)))
        lines.append(f"<span style='color:#777; font-size:11px'>"
                     f"{tr('status.tracking_hint')}</span>")
        self.text.setStyleSheet("color: #1b1b1b;")
        self.text.setText("<br>".join(lines))
