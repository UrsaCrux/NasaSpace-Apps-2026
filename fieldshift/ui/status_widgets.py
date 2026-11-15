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

    # (SummaryTile tile)
    def __init__(self, tile, parent=None):
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
        trend = QtWidgets.QLabel(trend_text(row))
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
        prefix = f"<b>{tr('status.upcoming')}</b> " if alert.upcoming else ""
        text = QtWidgets.QLabel(f"{icon} {prefix}{tr(alert.text_key, **alert.params)}")
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


# a section card: title, optional note (crop stage), optional soil
# triangle, table (left) and chart (right), and its alerts
class SectionCard(QtWidgets.QFrame):

    # (StatusSection section)
    def __init__(self, section, parent=None):
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
        title = QtWidgets.QLabel(f"{section.icon} <b>{tr(section.title_key)}</b>")
        title.setStyleSheet("font-size: 15px; border: none;")
        layout.addWidget(title)
        if section.note_key:
            params = {k: tr(v) if isinstance(v, str) and v.startswith("status.") else v
                      for k, v in section.note_params.items()}
            note = QtWidgets.QLabel(tr(section.note_key, **params))
            note.setStyleSheet("color: #2e7d32; border: none;")
            layout.addWidget(note)
        if section.texture is not None:
            layout.addWidget(self._texture_box(section.texture))

        self.table = StatusTable(section.rows)
        self.chart = TimeChart()
        body = QtWidgets.QHBoxLayout()
        body.addWidget(self.table, 0)
        body.addWidget(self.chart, 1)
        layout.addLayout(body)
        self.table.itemSelectionChanged.connect(self._show_selected)
        first = next((r for r in section.rows if not r.fixed), section.rows[0])
        self.table.select_key(first.key)

        self.alert_rows = []
        for alert in section.alerts:
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
        text = QtWidgets.QLabel(tr("status.texture", name=name, sand=f"{figure.sand:.0f}",
                                   silt=f"{figure.silt:.0f}", clay=f"{figure.clay:.0f}")
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


# texture classes with their own hint text (the rest use "other")
_HINTS = ("sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "clay_loam",
          "sandy_clay_loam", "clay")
