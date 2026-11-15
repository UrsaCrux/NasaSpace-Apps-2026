"""Pieces of the Status panel: summary tiles, the table of a section, its
chart over time (line or bars, with a hover read-out) and the alert rows.
Pure Qt, no QGIS.
"""

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.status import CHART_BARS, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH
from fieldshift.ui.analysis_widgets import TextureTriangle

# colour of each level
LEVEL_COLORS = {LEVEL_OK: "#2e7d32", LEVEL_WATCH: "#ef8f00", LEVEL_ALERT: "#c62828"}
# chart colours
_LINE = QtGui.QColor("#2e7d32")
_BARS = QtGui.QColor("#1e88e5")
_MEAN = QtGui.QColor("#9e9e9e")
_GRID = QtGui.QColor("#e3e6e3")
_INK = QtGui.QColor("#333333")
_CURSOR = QtGui.QColor("#f9a825")


# (StatusRow row, float value)
# the value with the row's decimals and unit ("23.4 °C")
def format_value(row, value):
    text = f"{value:.{row.decimals}f}"
    return f"{text} {row.unit}" if row.unit else text


# (str iso_date)
# short date for charts and tables: "8 Nov" / "8 nov"
def short_date(iso_date):
    return f"{int(iso_date[8:10])} {tr(f'month_short.{int(iso_date[5:7])}')}"


# (StatusRow row, float value)
# the value with the row's decimals, without unit ("23.4")
def format_number(row, value):
    return f"{value:.{row.decimals}f}"


# (StatusRow row)
# the row name with its unit: "Rain (mm)"
def row_title(row):
    return f"{tr(row.label_key)} ({row.unit})" if row.unit else tr(row.label_key)


# (StatusRow row)
# "↑ 2.1" / "↓ 0.4" / "=": newest value against the period mean
def trend_text(row):
    change = row.change()
    if row.fixed or abs(change) < 10 ** -row.decimals:
        return "="
    return f"{'↑' if change > 0 else '↓'} {abs(change):.{row.decimals}f}"


# (str source)
# a source name, translated when it is an i18n key ("status.source.farmer")
def source_text(source):
    return tr(source) if source.startswith("status.") else source


# a tile of the "today" summary: icon, name, newest value and trend. click
# it to jump to its row
class SummaryTile(QtWidgets.QFrame):

    # (SummaryTile tile, int days)
    # days: length of the period the trend compares with
    def __init__(self, tile, days, parent=None):
        super().__init__(parent)
        self.tile = tile
        # emitted with (str section id, str row key) on click
        self.clicked = Event()
        row = tile.row
        color = LEVEL_COLORS.get(row.level, LEVEL_COLORS[LEVEL_OK])
        self.setObjectName("summaryTile")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame#summaryTile {{ background: white; border: 1px solid #d5dbd5;"
            f" border-left: 4px solid {color}; border-radius: 6px; }}"
            f" QFrame#summaryTile:hover {{ background: #f1f8f1; }}"
            f" QLabel {{ border: none; background: transparent; }}")
        self.setToolTip(tr("status.tile_tooltip"))
        name = QtWidgets.QLabel(f"{tile.icon} {tr(row.label_key)}")
        name.setStyleSheet("color: #555; font-size: 11px;")
        value = QtWidgets.QLabel(f"<b>{format_value(row, row.latest())}</b>")
        value.setStyleSheet("font-size: 16px; color: #1b1b1b;")
        trend = QtWidgets.QLabel(tr("status.tile_trend", trend=trend_text(row), days=days))
        trend.setStyleSheet(f"color: {color}; font-size: 11px;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        for label in (name, value, trend):
            layout.addWidget(label)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.tile.section, self.tile.row.key)
        super().mouseReleaseEvent(event)


# table of the rows of a section: variable, newest, mean, min, max, trend.
# picking a row shows it in the chart
class StatusTable(QtWidgets.QTableWidget):

    COLUMNS = ("status.col.variable", "status.col.latest", "status.col.mean",
               "status.col.range", "status.col.trend")

    # (tuple rows)
    def __init__(self, rows, parent=None):
        super().__init__(len(rows), len(self.COLUMNS), parent)
        self.rows = rows
        self.setHorizontalHeaderLabels([tr(k) for k in self.COLUMNS])
        self.verticalHeader().hide()
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setStyleSheet("QTableWidget { border: 1px solid #d5dbd5; border-radius: 4px; }"
                           " QTableWidget::item:selected { background: #c8e6c9; color: black; }")
        header = self.horizontalHeader()
        for column in range(len(self.COLUMNS)):
            header.setSectionResizeMode(column,
                                        QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        for i, row in enumerate(rows):
            dot = QtGui.QColor(LEVEL_COLORS.get(row.level, LEVEL_COLORS[LEVEL_OK]))
            name = QtWidgets.QTableWidgetItem(f"● {row_title(row)}")
            name.setForeground(QtGui.QBrush(dot))
            name.setToolTip(tr("status.source", source=source_text(row.source))
                            + (f"\n{tr('status.fixed_tooltip')}" if row.fixed else ""))
            cells = [name, format_number(row, row.latest())]
            if row.fixed:
                cells += ["—", "—", tr("status.fixed")]
            else:
                cells += [format_number(row, row.mean()),
                          f"{format_number(row, min(row.values))} – "
                          f"{format_number(row, max(row.values))}", trend_text(row)]
            for column, cell in enumerate(cells):
                item = cell if isinstance(cell, QtWidgets.QTableWidgetItem) \
                    else QtWidgets.QTableWidgetItem(cell)
                if column:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.setItem(i, column, item)
        self.resizeRowsToContents()
        self.resizeColumnsToContents()
        # wide enough to never cut a text
        self.setMinimumWidth(sum(header.sectionSize(c) for c in range(len(self.COLUMNS)))
                             + 2 * self.frameWidth() + 4)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        height = self.horizontalHeader().height() + sum(
            self.rowHeight(i) for i in range(len(rows))) + 4
        self.setFixedHeight(height)

    # (str key)
    # selects the row with that key; returns True when found
    def select_key(self, key):
        for i, row in enumerate(self.rows):
            if row.key == key:
                self.selectRow(i)
                return True
        return False


# chart of one row over time: a line, or bars (rain), with the period mean
# dashed. moving the mouse over it shows the value of that day
class TimeChart(QtWidgets.QWidget):

    def __init__(self, row=None, parent=None):
        super().__init__(parent)
        self.row = row
        self.hover = None              # index of the day under the mouse
        self.setMouseTracking(True)
        self.setMinimumSize(220, 170)

    # (StatusRow row)
    # shows another row
    def set_row(self, row):
        self.row, self.hover = row, None
        self.update()

    # (low, high) of the value axis
    def _range(self):
        values, bars = self.row.values, self.row.chart == CHART_BARS
        low, high = (0.0 if bars else min(values)), max(values)
        if high == low:
            high, low = high + 1, low - (0 if bars else 1)
        if not bars:
            pad = (high - low) * 0.1
            low, high = low - pad, high + pad
        return low, high

    def _plot(self):
        metrics = self.fontMetrics()
        left = max(metrics.horizontalAdvance(format_number(self.row, v))
                   for v in self._range()) + 12
        top = metrics.height() + 10
        return QtCore.QRectF(left, top, self.width() - left - 10,
                             self.height() - top - metrics.height() - 8)

    def _x(self, plot, i):
        n = len(self.row.values)
        if self.row.chart == CHART_BARS:
            return plot.left() + plot.width() * (i + 0.5) / n
        return plot.left() + plot.width() * i / max(1, n - 1)

    def mouseMoveEvent(self, event):
        if self.row is None or self.row.fixed:
            return
        plot, n = self._plot(), len(self.row.values)
        x = event.position().x()
        self.hover = min(range(n), key=lambda i: abs(self._x(plot, i) - x))
        self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        row = self.row
        if row is None or row.fixed:
            painter.setPen(_MEAN)
            text = tr("status.no_chart") if row is not None else ""
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, text)
            return
        values, plot, metrics = row.values, self._plot(), self.fontMetrics()
        bars = row.chart == CHART_BARS
        low, high = self._range()

        def y(v):
            return plot.bottom() - plot.height() * (v - low) / (high - low)

        # title, frame, scale, dates
        painter.setPen(_INK)
        title = metrics.elidedText(row_title(row), QtCore.Qt.TextElideMode.ElideRight,
                                   int(self.width() - 4))
        painter.drawText(QtCore.QPointF(2, metrics.ascent() + 2), title)
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.drawRect(plot)
        painter.setPen(_INK)
        for v in (low, high):
            painter.drawText(QtCore.QRectF(0, y(v) - metrics.height() / 2, plot.left() - 6,
                                           metrics.height()),
                             QtCore.Qt.AlignmentFlag.AlignRight
                             | QtCore.Qt.AlignmentFlag.AlignVCenter, f"{v:.{row.decimals}f}")
        first, last = short_date(row.dates[0]), short_date(row.dates[-1])
        last_x = plot.right() - metrics.horizontalAdvance(last)
        if plot.left() + metrics.horizontalAdvance(first) + 12 < last_x:
            painter.drawText(QtCore.QPointF(plot.left(), self.height() - 4), first)
        painter.drawText(QtCore.QPointF(last_x, self.height() - 4), last)

        # the values
        if bars:
            width = plot.width() / len(values) * 0.7
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            for i, v in enumerate(values):
                color = QtGui.QColor(_BARS)
                if self.hover is not None and i != self.hover:
                    color.setAlpha(140)
                painter.setBrush(color)
                painter.drawRect(QtCore.QRectF(self._x(plot, i) - width / 2, y(v), width,
                                               plot.bottom() - y(v)))
        else:
            path = QtGui.QPainterPath(QtCore.QPointF(self._x(plot, 0), y(values[0])))
            for i, v in enumerate(values[1:], 1):
                path.lineTo(QtCore.QPointF(self._x(plot, i), y(v)))
            painter.setPen(QtGui.QPen(_LINE, 2))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        # mean of the period, dashed
        pen = QtGui.QPen(_MEAN, 1, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(plot.left(), y(row.mean())),
                         QtCore.QPointF(plot.right(), y(row.mean())))

        # read-out of the day under the mouse
        if self.hover is not None:
            x, v = self._x(plot, self.hover), values[self.hover]
            painter.setPen(QtGui.QPen(_CURSOR, 1.5))
            painter.drawLine(QtCore.QPointF(x, plot.top()), QtCore.QPointF(x, plot.bottom()))
            if not bars:
                painter.setBrush(_CURSOR)
                painter.drawEllipse(QtCore.QPointF(x, y(v)), 4, 4)
            text = f"{short_date(row.dates[self.hover])}: {format_value(row, v)}"
            box = QtCore.QRectF(0, 0, metrics.horizontalAdvance(text) + 12, metrics.height() + 6)
            box.moveTopLeft(QtCore.QPointF(min(x + 8, plot.right() - box.width()),
                                           plot.top() + 4))
            painter.setPen(QtGui.QPen(QtGui.QColor("#c9d1c9"), 1))
            painter.setBrush(QtGui.QColor(255, 255, 255, 235))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(_INK)
            painter.drawText(box, QtCore.Qt.AlignmentFlag.AlignCenter, text)
        painter.end()


# one warning: coloured bar, icon, text and, when there is a suggestion,
# a "See suggestion →" link
class AlertRow(QtWidgets.QFrame):

    # (StatusAlert alert)
    def __init__(self, alert, parent=None):
        super().__init__(parent)
        self.alert = alert
        # emitted with no arguments when "See suggestion" is clicked
        self.suggestion_requested = Event()
        color = LEVEL_COLORS.get(alert.level, LEVEL_COLORS[LEVEL_WATCH])
        self.setObjectName("alertRow")
        # a very light tint of the level colour (Qt reads "#rrggbbaa" as
        # "#aarrggbb", so use rgba)
        tint = QtGui.QColor(color)
        self.setStyleSheet(
            f"QFrame#alertRow {{ background: rgba({tint.red()}, {tint.green()}, {tint.blue()},"
            f" 22); border-left: 4px solid {color};"
            f" border-radius: 4px; }} QLabel {{ background: transparent; border: none; }}")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        icon = "🔮" if alert.upcoming else ("⛔" if alert.level == LEVEL_ALERT else "⚠️")
        text = QtWidgets.QLabel(f"{icon} {tr(alert.text_key, **alert.params)}")
        text.setWordWrap(True)
        layout.addWidget(text, 1)
        if alert.suggestion:
            self.link = QtWidgets.QPushButton(tr("status.see_suggestion"))
            self.link.setFlat(True)
            self.link.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.link.setStyleSheet("QPushButton { color: #1565c0; border: none; }"
                                    " QPushButton:hover { text-decoration: underline; }")
            self.link.clicked.connect(lambda: self.suggestion_requested.emit())
            layout.addWidget(self.link)


# variables of the forecast chart: key, icon, i18n label, unit, decimals
FORECAST_VARIABLES = (("temp", "🌡️", "status.fc.temp", "°C", 0),
                      ("rain", "🌧️", "status.fc.rain", "mm", 1),
                      ("wind", "💨", "status.fc.wind", "km/h", 0),
                      ("humidity", "💧", "status.fc.humidity", "%", 0),
                      ("radiation", "☀️", "status.fc.radiation", "MJ/m²", 1))
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

    # (str variable, int selected)
    def show_day(self, variable, selected):
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
        for i, day in enumerate(self.days):
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
                if chance is not None:
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
class UpcomingCard(QtWidgets.QFrame):

    # (list alerts, tuple days)
    # days: api.forecast.DayForecast, today first (may be empty)
    def __init__(self, alerts, days=(), parent=None):
        super().__init__(parent)
        self.alerts = list(alerts)
        self.days = tuple(days)
        self.variable = "temp"
        # emitted with no arguments when an alert's "See suggestion" is clicked
        self.suggestion_requested = Event()
        self.setObjectName("upcomingCard")
        self.setStyleSheet("QFrame#upcomingCard { background: #f3f0fa; border: 1px solid #c9bfe3;"
                           " border-radius: 8px; } QLabel { background: transparent;"
                           " border: none; }"
                           " QPushButton#fcVar { background: white; border: 1px solid #c9bfe3;"
                           " padding: 3px 8px; }"
                           " QPushButton#fcVar:checked { background: #6a1b9a; color: white; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)
        title = QtWidgets.QLabel(f"🔮 <b>{tr('status.upcoming_title')}</b>")
        title.setStyleSheet("font-size: 15px;")
        layout.addWidget(title)
        self.chart = self.slider = self.detail = None
        if self.days:
            self._build_forecast(layout)
        self.alert_rows = []
        if not self.alerts:
            none = QtWidgets.QLabel(tr("status.upcoming_none"))
            none.setStyleSheet("color: #555;")
            layout.addWidget(none)
        for alert in self.alerts:
            row = AlertRow(alert)
            row.suggestion_requested.connect(self.suggestion_requested.emit)
            layout.addWidget(row)
            self.alert_rows.append(row)

    def _build_forecast(self, layout):
        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(0)
        group = QtWidgets.QButtonGroup(self)
        self.variable_buttons = {}
        for key, icon, label, _, _ in FORECAST_VARIABLES:
            button = QtWidgets.QPushButton(f"{icon} {tr(label)}")
            button.setObjectName("fcVar")
            button.setCheckable(True)
            button.setChecked(key == self.variable)
            button.clicked.connect(lambda _=False, k=key: self.set_variable(k))
            group.addButton(button)
            buttons.addWidget(button)
            self.variable_buttons[key] = button
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.chart = ForecastChart(self.days)
        self.chart.day_clicked.connect(lambda i: self.slider.setValue(i))
        layout.addWidget(self.chart)

        controls = QtWidgets.QHBoxLayout()
        self.play_button = QtWidgets.QPushButton("▶")
        self.play_button.setFixedWidth(34)
        self.play_button.setToolTip(tr("status.fc.play"))
        self.play_button.clicked.connect(self.toggle_play)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, len(self.days) - 1)
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
        self.detail.setStyleSheet("QLabel { background: white; border: 1px solid #e0d8f0;"
                                  " border-radius: 6px; padding: 6px 8px; }")
        layout.addWidget(self.detail)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(900)
        self._timer.timeout.connect(self._step)
        self.show_day(0)

    # (str variable)
    # draws another FORECAST_VARIABLES key in the chart
    def set_variable(self, variable):
        self.variable = variable
        self.variable_buttons[variable].setChecked(True)
        self.chart.show_day(variable, self.slider.value())

    # (int index)
    # marks the day number index and shows its details
    def show_day(self, index):
        from fieldshift.ui.weather_card import SKY_ICONS
        day = self.days[index]
        self.chart.show_day(self.variable, index)

        def part(key, value, decimals, unit):
            return None if value is None else tr(key, value=f"{value:.{decimals}f}", unit=unit)
        rain = tr("status.fc.d_rain", value=f"{day.rain_mm:.1f}")
        if day.rain_chance is not None:
            rain += f" ({day.rain_chance:.0f}%)"
        parts = [tr("status.fc.d_temp", tmax=f"{day.tmax:.0f}", tmin=f"{day.tmin:.0f}"), rain,
                 part("status.fc.d_wind", day.wind_kmh, 0, "km/h"),
                 part("status.fc.d_humidity", day.humidity, 0, "%"),
                 part("status.fc.d_radiation", day.radiation, 1, "MJ/m²")]
        text = (f"<span style='font-size:18px'>{SKY_ICONS.get(day.sky, '')}</span> "
                f"<b>{day_label(index, day.date)}</b> · {short_date(day.date)}<br>"
                + " · ".join(p for p in parts if p))
        warnings = [a for a in self.alerts if a.date == day.date]
        for alert in warnings:
            color = LEVEL_COLORS.get(alert.level, LEVEL_COLORS[LEVEL_WATCH])
            text += (f"<br><span style='color:{color}'>⚠ "
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


# a section card: title, optional note (crop stage), optional soil
# triangle, table (left) and chart (right), and its alerts
class SectionCard(QtWidgets.QFrame):

    # (StatusSection section, int days)
    # days: length of the period shown (the dates come from the rows)
    def __init__(self, section, days, parent=None):
        super().__init__(parent)
        self.section = section
        # emitted with no arguments when an alert's "See suggestion" is clicked
        self.suggestion_requested = Event()
        self.setObjectName("sectionCard")
        self.setStyleSheet("QFrame#sectionCard { background: white; border: 1px solid #d5dbd5;"
                           " border-radius: 8px; }")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        dates = next((r.dates for r in section.rows if not r.fixed),
                     section.rows[0].dates if section.rows else ("", ""))
        period = tr("status.period_title", days=days, start=_date_or_dash(dates[0]),
                    end=_date_or_dash(dates[-1]))
        title = QtWidgets.QLabel(
            f"{section.icon} <b>{tr(section.title_key)}</b>"
            f" <span style='color:#666; font-size:12px;'>· {period}</span>")
        title.setStyleSheet("font-size: 15px; border: none;")
        layout.addWidget(title)
        if section.note_key:
            params = {k: tr(v) if isinstance(v, str) and v.startswith("status.")
                      else _date_or_dash(v) if k == "date" else v
                      for k, v in section.note_params.items()}
            note = QtWidgets.QLabel(tr(section.note_key, **params))
            note.setStyleSheet("color: #2e7d32; border: none;")
            layout.addWidget(note)
        if section.texture is not None:
            layout.addWidget(self._texture_box(section.texture))

        self.table = self.chart = None
        if section.rows:
            self.table = StatusTable(section.rows)
            self.chart = TimeChart()
            body = QtWidgets.QHBoxLayout()
            body.addWidget(self.table, 0)
            body.addWidget(self.chart, 1)
            layout.addLayout(body)
            self.table.itemSelectionChanged.connect(self._show_selected)
            first = next((r for r in section.rows if not r.fixed), section.rows[0])
            self.table.select_key(first.key)
        else:
            empty = QtWidgets.QLabel(tr("status.no_data"))
            empty.setStyleSheet("color: #777; border: none;")
            layout.addWidget(empty)

        self.alert_rows = []
        observed = [a for a in section.alerts if not a.upcoming]
        if observed:
            heading = QtWidgets.QLabel(tr("status.observed_alerts", days=days))
            heading.setStyleSheet("color: #555; font-size: 11px; border: none;")
            layout.addWidget(heading)
        for alert in observed:
            row = AlertRow(alert)
            row.suggestion_requested.connect(self.suggestion_requested.emit)
            layout.addWidget(row)
            self.alert_rows.append(row)

    def _texture_box(self, figure):
        box = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        triangle = TextureTriangle(figure)
        triangle.setMinimumSize(300, 260)
        triangle.setMaximumHeight(300)
        row.addWidget(triangle, 3)
        name = tr(f"data_fields.soil_texture.{figure.texture}") if figure.texture else "—"
        if figure.sand is not None:
            heading = tr("status.texture", name=name, sand=f"{figure.sand:.0f}",
                         silt=f"{figure.silt:.0f}", clay=f"{figure.clay:.0f}")
        else:
            heading = f"<b>{name}</b>"
            if not figure.texture:
                heading += "<br>" + tr("status.texture_missing")
        text = QtWidgets.QLabel(heading
                                + "<br><br>" + tr(f"status.texture_hint.{figure.texture}"
                                                  if figure.texture in _HINTS
                                                  else "status.texture_hint.other"))
        text.setWordWrap(True)
        text.setStyleSheet("border: none;")
        row.addWidget(text, 2)
        return box

    def _show_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.chart.set_row(self.section.rows[rows[0].row()])


# (str iso_date)
# short date, or "—" for an empty / non-date value
def _date_or_dash(value):
    return short_date(value) if isinstance(value, str) and len(value) >= 10 else "—"


# texture classes with their own hint text (the rest use "other")
_HINTS = ("sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "clay_loam",
          "sandy_clay_loam", "clay")
