"""Small drawing widgets for the analysis tabs: a line chart over time and a
preview of the field coloured by a value. Pure Qt, no QGIS.

The field preview is a stand-in for a real map: when the analyses read
rasters, it will be replaced by a MapView showing them.
"""

import math
import re

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets

# i18n keys that can appear inside analysis values ("month.7", "crop.wheat")
_KEY_IN_TEXT = re.compile(r"\b(?:month|crop)\.[a-z0-9_]+\b")

# colour scales: list of (position 0..1, colour)
PALETTES = {
    "temperature": [(0.0, "#2c7bb6"), (0.5, "#f7f7f7"), (1.0, "#d7191c")],
    "vegetation": [(0.0, "#8c510a"), (0.45, "#f6e8c3"), (1.0, "#1a9641")],
    "water": [(0.0, "#d7191c"), (0.5, "#f7f7f7"), (1.0, "#2c7bb6")],
    "suitability": [(0.0, "#d7191c"), (0.5, "#ffffbf"), (1.0, "#1a9641")],
}

_INK = QtGui.QColor("#333333")
_GRID = QtGui.QColor("#dddddd")
_LINE = QtGui.QColor("#2e7d32")
_CURSOR = QtGui.QColor("#f9a825")


# (str text)
# text with the i18n keys it contains ("month.7", "crop.wheat") translated
def localize(text):
    return _KEY_IN_TEXT.sub(lambda m: tr(m.group(0)), str(text))


# (str date)
# "2025-07" as "July 2025" in the current language
def format_date(date):
    return f"{tr(f'month.{int(date[5:7])}')} {date[:4]}"


# (str palette, float t)
# colour of the position t (0..1) of a palette
def palette_color(palette, t):
    stops = PALETTES.get(palette, PALETTES["suitability"])
    t = min(1.0, max(0.0, t))
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            f = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            a, b = QtGui.QColor(c0), QtGui.QColor(c1)
            return QtGui.QColor(round(a.red() + (b.red() - a.red()) * f),
                                round(a.green() + (b.green() - a.green()) * f),
                                round(a.blue() + (b.blue() - a.blue()) * f))
    return QtGui.QColor(stops[-1][1])


def _number(value, unit):
    text = f"{value:g}"
    return f"{text} {unit}" if unit else text


# line chart of one Series, with a vertical cursor on the selected date
class LineChart(QtWidgets.QWidget):

    # (Series series, QWidget parent = None)
    # draws series; the cursor starts on its last date
    def __init__(self, series, parent=None):
        super().__init__(parent)
        self.series = series
        self.cursor = len(series.values) - 1
        self.setMinimumSize(260, 150)

    # (int index)
    # moves the cursor to the date number index
    def set_cursor(self, index):
        self.cursor = max(0, min(index, len(self.series.values) - 1))
        self.update()

    def paintEvent(self, event):
        values = self.series.values
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        metrics = self.fontMetrics()
        left, right = metrics.horizontalAdvance("-000.0") + 8, 10
        top, bottom = 10, metrics.height() + 8
        plot = QtCore.QRectF(left, top, self.width() - left - right,
                             self.height() - top - bottom)
        low, high = min(values), max(values)
        if high == low:
            high, low = high + 1, low - 1
        pad = (high - low) * 0.08
        low, high = low - pad, high + pad

        def point(i, v):
            x = plot.left() + plot.width() * i / max(1, len(values) - 1)
            y = plot.bottom() - plot.height() * (v - low) / (high - low)
            return QtCore.QPointF(x, y)

        # frame, min / max labels, zero line, first / last date
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.drawRect(plot)
        if low < 0 < high:
            painter.drawLine(point(0, 0), point(len(values) - 1, 0))
        painter.setPen(_INK)
        painter.drawText(QtCore.QRectF(0, plot.top() - 2, left - 6, metrics.height()),
                         QtCore.Qt.AlignmentFlag.AlignRight, f"{high:.1f}")
        painter.drawText(QtCore.QRectF(0, plot.bottom() - metrics.height() + 2, left - 6,
                                       metrics.height()),
                         QtCore.Qt.AlignmentFlag.AlignRight, f"{low:.1f}")
        dates = self.series.dates
        painter.drawText(QtCore.QPointF(plot.left(), self.height() - 4), format_date(dates[0]))
        last = format_date(dates[-1])
        painter.drawText(QtCore.QPointF(plot.right() - metrics.horizontalAdvance(last),
                                        self.height() - 4), last)

        # the line
        path = QtGui.QPainterPath(point(0, values[0]))
        for i, v in enumerate(values[1:], 1):
            path.lineTo(point(i, v))
        painter.setPen(QtGui.QPen(_LINE, 2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # the cursor
        p = point(self.cursor, values[self.cursor])
        painter.setPen(QtGui.QPen(_CURSOR, 2))
        painter.drawLine(QtCore.QPointF(p.x(), plot.top()), QtCore.QPointF(p.x(), plot.bottom()))
        painter.setBrush(_CURSOR)
        painter.drawEllipse(p, 4.5, 4.5)
        painter.end()


# the field's outline filled with a grid of coloured cells (one MapFrames
# date at a time), with a colour legend below
class FieldPreview(QtWidgets.QWidget):

    # (list vertices, MapFrames frames, QWidget parent = None)
    # draws the last date of frames inside the polygon of vertices (lon, lat)
    def __init__(self, vertices, frames, parent=None):
        super().__init__(parent)
        self.vertices = list(vertices)
        self.frames = frames
        self.frame = len(frames.grids) - 1
        self.setMinimumSize(220, 180)

    # (int index)
    # shows the grid of the date number index
    def set_frame(self, index):
        self.frame = max(0, min(index, len(self.frames.grids) - 1))
        self.update()

    # ()
    # colour of every cell of the shown date, row by row (for tests)
    def cell_colors(self):
        f = self.frames
        return [[palette_color(f.palette, (v - f.low) / (f.high - f.low)).name() for v in row]
                for row in f.grids[self.frame]]

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        metrics = self.fontMetrics()
        legend_h = metrics.height() * 2 + 10
        area = QtCore.QRectF(10, 10, self.width() - 20, self.height() - 20 - legend_h)

        # project lon/lat to a flat picture (east to the right, north up)
        lat0 = math.radians(sum(v[1] for v in self.vertices) / len(self.vertices))
        xs = [v[0] * math.cos(lat0) for v in self.vertices]
        ys = [-v[1] for v in self.vertices]
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1e-9
        scale = min(area.width(), area.height()) / span
        ox = area.left() + (area.width() - (max(xs) - min(xs)) * scale) / 2
        oy = area.top() + (area.height() - (max(ys) - min(ys)) * scale) / 2

        def to_px(x, y):
            return QtCore.QPointF(ox + (x - min(xs)) * scale, oy + (y - min(ys)) * scale)

        outline = QtGui.QPolygonF([to_px(x, y) for x, y in zip(xs, ys)])
        path = QtGui.QPainterPath()
        path.addPolygon(outline)
        path.closeSubpath()
        box = outline.boundingRect()

        # cells, clipped to the field
        grid = self.frames.grids[self.frame]
        rows, cols = len(grid), len(grid[0])
        colors = self.cell_colors()
        painter.save()
        painter.setClipPath(path)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for r in range(rows):
            for c in range(cols):
                painter.setBrush(QtGui.QColor(colors[r][c]))
                painter.drawRect(QtCore.QRectF(box.left() + box.width() * c / cols,
                                               box.top() + box.height() * r / rows,
                                               box.width() / cols + 0.6, box.height() / rows + 0.6))
        painter.restore()
        painter.setPen(QtGui.QPen(_INK, 2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # legend: colour ramp from low to high
        f = self.frames
        ramp = QtCore.QRectF(20, self.height() - legend_h + 4, self.width() - 40, 10)
        gradient = QtGui.QLinearGradient(ramp.topLeft(), ramp.topRight())
        for position, color in PALETTES.get(f.palette, PALETTES["suitability"]):
            gradient.setColorAt(position, QtGui.QColor(color))
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.setBrush(QtGui.QBrush(gradient))
        painter.drawRect(ramp)
        painter.setPen(_INK)
        text_y = ramp.bottom() + metrics.height()
        painter.drawText(QtCore.QPointF(ramp.left(), text_y), _number(f.low, f.unit))
        high = _number(f.high, f.unit)
        painter.drawText(QtCore.QPointF(ramp.right() - metrics.horizontalAdvance(high), text_y), high)
        painter.end()
