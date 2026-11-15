"""Pieces of the Trends panel: milestone tiles, the seasons table, the
table of a section and its 12-month chart (this year, the year before and
the normal, with a hover read-out). Pure Qt, no QGIS.
"""

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.status import CHART_BARS
from fieldshift.ui.status_widgets import source_text

# colours of the three series
_THIS = QtGui.QColor("#2e7d32")
_BARS = QtGui.QColor("#1e88e5")
_PREVIOUS = QtGui.QColor("#ef8f00")
_NORMAL = QtGui.QColor("#8d8d8d")
_GRID = QtGui.QColor("#e3e6e3")
_INK = QtGui.QColor("#333333")
_CURSOR = QtGui.QColor("#f9a825")

_CARD = ("QFrame#{name} {{ background: white; border: 1px solid #d5dbd5; border-radius: 8px; }}"
         " QLabel {{ border: none; background: transparent; }}")


# (str month)
# "Mar 26" / "mar 26" for "2026-03"
def short_month(month):
    return f"{tr(f'month_short.{int(month[5:7])}')} {month[2:4]}"


# (str month)
# "March 2026" for "2026-03"
def long_month(month):
    return f"{tr(f'month.{int(month[5:7])}')} {month[:4]}"


# (float value, int decimals, str unit = "")
# a value, or "—" when None
def number(value, decimals, unit=""):
    if value is None:
        return "—"
    text = f"{value:.{decimals}f}"
    return f"{text} {unit}" if unit else text


# (TrendRow row)
# the row name with its unit and what the year column means ("sum"/"mean")
def row_title(row):
    unit = f" ({row.unit})" if row.unit else ""
    return f"{tr(row.label_key)}{unit}"


# a titled white card with a vertical layout (card.body)
class Card(QtWidgets.QFrame):

    # (str title, str name = "trendCard")
    def __init__(self, title, name="trendCard", parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.setStyleSheet(_CARD.format(name=name))
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(12, 10, 12, 12)
        self.body.setSpacing(8)
        label = QtWidgets.QLabel(title)
        label.setStyleSheet("font-size: 15px;")
        self.body.addWidget(label)


# the notable facts of the year as small tiles (3 per row)
class MilestonesCard(Card):

    # (tuple milestones)
    def __init__(self, milestones, parent=None):
        super().__init__(f"⭐ <b>{tr('trends.milestones')}</b>", "milestonesCard", parent)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        for i, item in enumerate(milestones):
            tile = QtWidgets.QLabel(
                f"<span style='font-size:16px'>{item.icon}</span> "
                f"<span style='color:#555'>{tr(item.label_key)}</span><br>"
                f"<b>{item.value}</b>"
                + (f" <span style='color:#666'>· {long_month(item.month)}</span>"
                   if item.month else ""))
            tile.setStyleSheet("background: #f6f8f6; border: 1px solid #e0e5e0;"
                               " border-radius: 6px; padding: 6px;")
            tile.setWordWrap(True)
            grid.addWidget(tile, i // 3, i % 3)
        self.body.addLayout(grid)
        self.tiles = grid.count()


# a table of the seasons: temperature, rain, water balance, NDVI, soil
class SeasonsCard(Card):

    COLUMNS = (("temp", "°C", 1), ("rain", "mm", 0), ("water_balance", "mm", 0),
               ("ndvi", "", 2), ("soil_moisture", "%", 0))

    # (tuple seasons)
    def __init__(self, seasons, parent=None):
        super().__init__(f"🗓️ <b>{tr('trends.seasons')}</b>", "seasonsCard", parent)
        table = QtWidgets.QTableWidget(len(seasons), len(self.COLUMNS) + 1)
        table.setHorizontalHeaderLabels(
            [tr("trends.col.season")]
            + [tr(f"trends.season_col.{key}") + (f" ({unit})" if unit else "")
               for key, unit, _ in self.COLUMNS])
        table.verticalHeader().hide()
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setAlternatingRowColors(True)
        for r, season in enumerate(seasons):
            first, last = season.months[0], season.months[-1]
            name = QtWidgets.QTableWidgetItem(f"{tr(season.name_key)} {season.year}")
            name.setToolTip(f"{long_month(first)} – {long_month(last)}")
            table.setItem(r, 0, name)
            for c, (key, _, decimals) in enumerate(self.COLUMNS, 1):
                value = season.values.get(key)
                item = QtWidgets.QTableWidgetItem(number(value, decimals))
                item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if key == "water_balance" and value is not None:
                    item.setForeground(QtGui.QBrush(QtGui.QColor(
                        "#c62828" if value < 0 else "#1565c0")))
                table.setItem(r, c, item)
        header = table.horizontalHeader()
        for c in range(table.columnCount()):
            header.setSectionResizeMode(c, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        table.resizeRowsToContents()
        table.setFixedHeight(header.height() + sum(table.rowHeight(r)
                                                   for r in range(len(seasons))) + 4)
        table.setStyleSheet("QTableWidget { border: 1px solid #d5dbd5; }")
        hint = QtWidgets.QLabel(tr("trends.seasons_hint"))
        hint.setStyleSheet("color: #666; font-size: 11px;")
        hint.setWordWrap(True)
        self.body.addWidget(table)
        self.body.addWidget(hint)
        self.table = table


# table of the rows of a section: the last 12 months, the year before, the
# normal and the difference. picking a row shows it in the chart
class TrendTable(QtWidgets.QTableWidget):

    COLUMNS = ("trends.col.variable", "trends.col.year", "trends.col.previous",
               "trends.col.normal", "trends.col.change")

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
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QTableWidget { border: 1px solid #d5dbd5; border-radius: 4px; }"
                           " QTableWidget::item:selected { background: #c8e6c9; color: black; }")
        for i, row in enumerate(rows):
            name = QtWidgets.QTableWidgetItem(row_title(row))
            name.setToolTip(tr("status.source", source=source_text(row.source)) + "\n"
                            + tr(f"trends.aggregate.{row.aggregate}"))
            year, prev, normal = row.total(), row.previous_total(), row.normal_total()
            base = normal if normal is not None else prev
            change = "—"
            if base is not None and year is not None:
                diff = year - base
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "="
                change = f"{arrow} {abs(diff):.{row.decimals}f}"
            cells = [name, number(year, row.decimals), number(prev, row.decimals),
                     number(normal, row.decimals), change]
            for column, cell in enumerate(cells):
                item = cell if isinstance(cell, QtWidgets.QTableWidgetItem) \
                    else QtWidgets.QTableWidgetItem(cell)
                if column:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                self.setItem(i, column, item)
        header = self.horizontalHeader()
        for column in range(len(self.COLUMNS)):
            header.setSectionResizeMode(column,
                                        QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.resizeRowsToContents()
        self.resizeColumnsToContents()
        self.setMinimumWidth(sum(header.sectionSize(c) for c in range(len(self.COLUMNS)))
                             + 2 * self.frameWidth() + 4)
        self.setFixedHeight(header.height() + sum(self.rowHeight(i)
                                                  for i in range(len(rows))) + 4)

    # (str key)
    # selects the row with that key; returns True when found
    def select_key(self, key):
        for i, row in enumerate(self.rows):
            if row.key == key:
                self.selectRow(i)
                return True
        return False


# 12-month chart of a row: this year (line, or bars for sums), the year
# before (dashed orange) and the normal (dotted grey); hover shows a month
class YearChart(QtWidgets.QWidget):

    def __init__(self, row=None, parent=None):
        super().__init__(parent)
        self.row = row
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(240, 200)

    # (TrendRow row)
    def set_row(self, row):
        self.row, self.hover = row, None
        self.update()

    def _series(self):
        row = self.row
        return [s for s in (row.values, row.previous, row.normal) if s]

    def _range(self):
        known = [v for s in self._series() for v in s if v is not None]
        low, high = min(known), max(known)
        if self.row.chart == CHART_BARS:
            low = min(0.0, low)
        if high == low:
            high, low = high + 1, low - 1
        pad = (high - low) * 0.08
        return (low if self.row.chart == CHART_BARS and low == 0 else low - pad), high + pad

    def _plot(self):
        metrics = self.fontMetrics()
        left = max(metrics.horizontalAdvance(number(v, self.row.decimals))
                   for v in self._range()) + 12
        top = 2 * metrics.height() + 12
        return QtCore.QRectF(left, top, self.width() - left - 10,
                             self.height() - top - metrics.height() - 8)

    def _x(self, plot, i):
        return plot.left() + plot.width() * (i + 0.5) / len(self.row.months)

    def mouseMoveEvent(self, event):
        if self.row is None:
            return
        plot, x = self._plot(), event.position().x()
        self.hover = min(range(len(self.row.months)), key=lambda i: abs(self._x(plot, i) - x))
        self.update()

    def leaveEvent(self, event):
        self.hover = None
        self.update()

    def paintEvent(self, event):
        if self.row is None:
            return
        row, painter = self.row, QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        metrics, plot = self.fontMetrics(), self._plot()
        low, high = self._range()
        bars = row.chart == CHART_BARS

        def y(v):
            return plot.bottom() - plot.height() * (v - low) / (high - low)

        # title and legend
        painter.setPen(_INK)
        painter.drawText(QtCore.QPointF(2, metrics.ascent() + 2), metrics.elidedText(
            row_title(row), QtCore.Qt.TextElideMode.ElideRight, int(self.width() - 4)))
        x = 2.0
        legend_y = metrics.height() + metrics.ascent() + 4
        for text, color, style, show in (
                (tr("trends.legend.year"), _BARS if bars else _THIS,
                 QtCore.Qt.PenStyle.SolidLine, True),
                (tr("trends.legend.previous"), _PREVIOUS, QtCore.Qt.PenStyle.DashLine,
                 bool(row.previous)),
                (tr("trends.legend.normal"), _NORMAL, QtCore.Qt.PenStyle.DotLine,
                 bool(row.normal))):
            if not show:
                continue
            painter.setPen(QtGui.QPen(color, 2, style))
            painter.drawLine(QtCore.QPointF(x, legend_y - 4), QtCore.QPointF(x + 16, legend_y - 4))
            painter.setPen(_INK)
            painter.drawText(QtCore.QPointF(x + 20, legend_y), text)
            x += 32 + metrics.horizontalAdvance(text)

        # frame, scale, zero, months
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.drawRect(plot)
        if low < 0 < high:
            painter.drawLine(QtCore.QPointF(plot.left(), y(0)), QtCore.QPointF(plot.right(), y(0)))
        painter.setPen(_INK)
        for v in (low, high):
            painter.drawText(QtCore.QRectF(0, y(v) - metrics.height() / 2, plot.left() - 6,
                                           metrics.height()),
                             QtCore.Qt.AlignmentFlag.AlignRight
                             | QtCore.Qt.AlignmentFlag.AlignVCenter, number(v, row.decimals))
        step = max(1, round(len(row.months) * (metrics.horizontalAdvance("Mmm 00") + 8)
                            / max(1.0, plot.width())))
        for i in range(0, len(row.months), step):
            text = short_month(row.months[i])
            painter.drawText(QtCore.QPointF(self._x(plot, i) - metrics.horizontalAdvance(text) / 2,
                                            self.height() - 4), text)

        # this year
        if bars:
            width = plot.width() / len(row.months) * 0.6
            base = y(max(low, 0.0))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            for i, v in enumerate(row.values):
                if v is None:
                    continue
                color = QtGui.QColor(_BARS if v >= 0 else QtGui.QColor("#e57373"))
                if self.hover is not None and i != self.hover:
                    color.setAlpha(150)
                painter.setBrush(color)
                top, bottom = sorted((y(v), base))
                painter.drawRect(QtCore.QRectF(self._x(plot, i) - width / 2, top, width,
                                               bottom - top))
        else:
            self._line(painter, plot, y, row.values, QtGui.QPen(_THIS, 2.2))
        if row.previous:
            self._line(painter, plot, y, row.previous,
                       QtGui.QPen(_PREVIOUS, 1.6, QtCore.Qt.PenStyle.DashLine))
        if row.normal:
            self._line(painter, plot, y, row.normal,
                       QtGui.QPen(_NORMAL, 1.6, QtCore.Qt.PenStyle.DotLine))

        # read-out of the month under the mouse
        if self.hover is not None:
            i = self.hover
            xh = self._x(plot, i)
            painter.setPen(QtGui.QPen(_CURSOR, 1.5))
            painter.drawLine(QtCore.QPointF(xh, plot.top()), QtCore.QPointF(xh, plot.bottom()))
            lines = [long_month(row.months[i]),
                     f"{tr('trends.legend.year')}: {number(row.values[i], row.decimals, row.unit)}"]
            if row.previous:
                lines.append(f"{tr('trends.legend.previous')}: "
                             f"{number(row.previous[i], row.decimals, row.unit)}")
            if row.normal:
                lines.append(f"{tr('trends.legend.normal')}: "
                             f"{number(row.normal[i], row.decimals, row.unit)}")
            width = max(metrics.horizontalAdvance(t) for t in lines) + 14
            box = QtCore.QRectF(0, 0, width, len(lines) * metrics.height() + 8)
            left = xh + 10 if xh + 10 + width < plot.right() else xh - 10 - width
            box.moveTopLeft(QtCore.QPointF(max(plot.left(), left), plot.top() + 4))
            painter.setPen(QtGui.QPen(QtGui.QColor("#c9d1c9"), 1))
            painter.setBrush(QtGui.QColor(255, 255, 255, 240))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(_INK)
            for n, text in enumerate(lines):
                painter.drawText(QtCore.QPointF(box.left() + 7,
                                                box.top() + 4 + metrics.ascent()
                                                + n * metrics.height()), text)
        painter.end()

    def _line(self, painter, plot, y, values, pen):
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        path, drawing = QtGui.QPainterPath(), False
        for i, v in enumerate(values):
            if v is None:
                drawing = False
                continue
            point = QtCore.QPointF(self._x(plot, i), y(v))
            if drawing:
                path.lineTo(point)
            else:
                path.moveTo(point)
                drawing = True
        painter.drawPath(path)


# a section: title, table (left) and 12-month chart (right)
class TrendSectionCard(Card):

    # (TrendSection section)
    def __init__(self, section, parent=None):
        super().__init__(f"{section.icon} <b>{tr(section.title_key)}</b>", "trendSection",
                         parent)
        self.section = section
        self.table = self.chart = None
        if not section.rows:
            empty = QtWidgets.QLabel(tr("status.no_data"))
            empty.setStyleSheet("color: #777;")
            self.body.addWidget(empty)
            return
        self.table = TrendTable(section.rows)
        self.chart = YearChart()
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.table, 0)
        row.addWidget(self.chart, 1)
        self.body.addLayout(row)
        self.table.itemSelectionChanged.connect(self._show_selected)
        self.table.select_key(section.rows[0].key)

    def _show_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.chart.set_row(self.section.rows[rows[0].row()])


# the crop of the field and a link to the suggestions (Analyze)
class CropCard(Card):

    # (str crop)
    def __init__(self, crop, parent=None):
        super().__init__(f"🌾 <b>{tr('trends.crop_title')}</b>", "cropCard", parent)
        # emitted with no arguments when "See suggestions" is clicked
        self.suggestion_requested = Event()
        text = QtWidgets.QLabel(tr("trends.crop_now", crop=crop) if crop
                                else tr("trends.crop_none"))
        text.setWordWrap(True)
        history = QtWidgets.QLabel(tr("trends.crop_history"))
        history.setWordWrap(True)
        history.setStyleSheet("color: #666;")
        link = QtWidgets.QPushButton(tr("trends.see_rotation"))
        link.setFlat(True)
        link.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        link.setStyleSheet("QPushButton { color: #1565c0; border: none; text-align: left; }"
                           " QPushButton:hover { text-decoration: underline; }")
        link.clicked.connect(lambda: self.suggestion_requested.emit())
        for widget in (text, history, link):
            self.body.addWidget(widget)
