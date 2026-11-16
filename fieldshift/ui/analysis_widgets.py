"""Small drawing widgets for the analysis tabs: a line chart over time, a
preview of the field coloured by a value and the USDA soil texture
triangle. Pure Qt, no QGIS.

The field preview is a stand-in for a real map: when the analyses read
rasters, it will be replaced by a MapView showing them.
"""

import math
import re

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets

# i18n keys that can appear inside analysis values ("month.7", "crop.wheat",
# "data_fields.soil_texture.loam", "analysis.crop_growth.mode.rainfed")
_KEY_IN_TEXT = re.compile(r"\b(?:month|crop)\.[a-z0-9_]+\b"
                          r"|\b(?:data_fields|analysis)\.[a-z0-9_]+(?:\.[a-z0-9_]+)+\b")

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
# "2025-07" as "July 2025", "2025-07-14" as "14 July 2025", in the current language
def format_date(date):
    text = f"{tr(f'month.{int(date[5:7])}')} {date[:4]}"
    return f"{int(date[8:10])} {text}" if len(date) >= 10 else text


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


# (Series series)
# the series name in the current language, with its parameters ("of Barley")
def series_title(series):
    params = {k: localize(v) for k, v in (getattr(series, "label_params", None) or {}).items()}
    return tr(series.label_key, **params)


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
        unit = self.series.unit
        data_low, data_high = min(values), max(values)
        if unit == "%":
            low, high = 0.0, 100.0            # a share: always the whole 0-100 scale
        else:
            low, high = data_low, data_high
            if high == low:
                high, low = high + 1, low - 1
            pad = (high - low) * 0.08
            low, high = low - pad, high + pad
        labels = [_number(round(v, 1), unit) for v in (low, high)] if unit == "%" else \
            [_number(round(v, 1), unit) for v in (data_low, data_high)]
        left = max(metrics.horizontalAdvance(t) for t in labels) + 10
        right, top, bottom = 10, metrics.height() + 12, metrics.height() + 8
        plot = QtCore.QRectF(left, top, self.width() - left - right,
                             self.height() - top - bottom)

        def point(i, v):
            x = plot.left() + plot.width() * i / max(1, len(values) - 1)
            y = plot.bottom() - plot.height() * (v - low) / (high - low)
            return QtCore.QPointF(x, y)

        # frame, min / max labels, zero line, first / last date
        painter.setPen(QtGui.QPen(_GRID, 1))
        painter.drawRect(plot)
        if low < 0 < high:
            painter.drawLine(point(0, 0), point(len(values) - 1, 0))
        # title (with the unit), and the value scale on the left: 0 and 100
        # for shares, else the lowest and highest value with dashed guides
        painter.setPen(_INK)
        title = series_title(self.series) + (f" ({unit})" if unit else "")
        painter.drawText(QtCore.QPointF(2, metrics.ascent() + 2), metrics.elidedText(
            title, QtCore.Qt.TextElideMode.ElideRight, int(self.width() - 4)))
        marks = (low, high) if unit == "%" else (data_low, data_high)
        for v, text in zip(marks, labels):
            if unit != "%":
                painter.setPen(QtGui.QPen(_GRID, 1, QtCore.Qt.PenStyle.DashLine))
                painter.drawLine(point(0, v), point(len(values) - 1, v))
                painter.setPen(_INK)
            painter.drawText(QtCore.QRectF(0, point(0, v).y() - metrics.height() / 2, left - 6,
                                           metrics.height()),
                             QtCore.Qt.AlignmentFlag.AlignRight
                             | QtCore.Qt.AlignmentFlag.AlignVCenter, text)
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


# USDA texture classes: polygon corners as (sand %, clay %), and the colour
# of each class (like the usual Spanish/English textbook triangle)
TEXTURE_POLYGONS = {
    "clay": [(0, 100), (45, 55), (45, 40), (20, 40), (0, 60)],
    "silty_clay": [(0, 60), (20, 40), (0, 40)],
    "sandy_clay": [(45, 55), (65, 35), (45, 35)],
    "clay_loam": [(20, 40), (45, 40), (45, 27), (20, 27)],
    "silty_clay_loam": [(0, 40), (20, 40), (20, 27), (0, 27)],
    "sandy_clay_loam": [(45, 35), (65, 35), (80, 20), (52, 20), (45, 27)],
    "loam": [(45, 27), (23, 27), (43, 7), (52, 7), (52, 20)],
    "silt_loam": [(23, 27), (0, 27), (0, 12), (8, 12), (20, 0), (50, 0), (43, 7)],
    "silt": [(0, 12), (0, 0), (20, 0), (8, 12)],
    "sandy_loam": [(52, 20), (52, 7), (43, 7), (50, 0), (70, 0), (85, 15), (80, 20)],
    "loamy_sand": [(70, 0), (85, 0), (90, 10), (85, 15)],
    "sand": [(85, 0), (100, 0), (90, 10)],
}
TEXTURE_COLORS = {
    "clay": "#e8231c", "silty_clay": "#f2632a", "sandy_clay": "#c73a12",
    "clay_loam": "#9c3d0c", "silty_clay_loam": "#f2862b", "sandy_clay_loam": "#a0693a",
    "loam": "#a8700f", "silt_loam": "#f6a94a", "silt": "#fcd47f",
    "sandy_loam": "#6e6a3a", "loamy_sand": "#1f6f6c", "sand": "#1c6d9c",
}


# label positions (sand %, clay %) of the classes too small for their centre
TEXTURE_LABEL_AT = {"sand": (96, 4), "loamy_sand": (79, 9)}


# the USDA texture triangle with the classes coloured, the field's class
# outlined and its point (clay, sand, silt) marked. Sand grows to the left
# along the base, silt to the right, clay to the top
class TextureTriangle(QtWidgets.QWidget):

    # (TextureFigure figure, QWidget parent = None)
    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self.figure = figure
        self.setMinimumSize(360, 320)

    # (float sand, float clay)
    # widget coordinates of a composition
    def point(self, sand, clay):
        left, base, side = self._geometry()
        silt = 100 - sand - clay
        x = left + (silt + clay / 2) / 100 * side
        y = base - clay / 100 * side * math.sqrt(3) / 2
        return QtCore.QPointF(x, y)

    def _geometry(self):
        margin = 46
        side = min(self.width() - 2 * margin, (self.height() - 2 * margin) * 2 / math.sqrt(3))
        left = (self.width() - side) / 2
        base = (self.height() + side * math.sqrt(3) / 2) / 2 + 6
        return left, base, side

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        chosen = self.figure.texture
        for name, corners in TEXTURE_POLYGONS.items():
            polygon = QtGui.QPolygonF([self.point(s, c) for s, c in corners])
            color = QtGui.QColor(TEXTURE_COLORS[name])
            if chosen and name != chosen:
                color.setAlpha(120)                  # the field's class stands out
            painter.setBrush(color)
            painter.setPen(QtGui.QPen(QtGui.QColor("#4a4a4a"), 1))
            painter.drawPolygon(polygon)
        # 10 % grid lines parallel to each side
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 45), 1))
        for v in range(10, 100, 10):
            painter.drawLine(self.point(100 - v, v), self.point(0, v))          # clay
            painter.drawLine(self.point(v, 0), self.point(v, 100 - v))          # sand
            painter.drawLine(self.point(0, 100 - v), self.point(100 - v, 0))    # silt
        # class names
        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        painter.setFont(font)
        for name, corners in TEXTURE_POLYGONS.items():
            cx = sum(s for s, _ in corners) / len(corners)
            cy = sum(c for _, c in corners) / len(corners)
            cx, cy = TEXTURE_LABEL_AT.get(name, (cx, cy))
            center = self.point(cx, cy)
            text = tr(f"data_fields.soil_texture.{name}")
            painter.setPen(QtGui.QColor("white" if name not in ("silt", "silt_loam") else "#333"))
            rect = QtCore.QRectF(center.x() - 50, center.y() - 14, 100, 28)
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter
                             | QtCore.Qt.TextFlag.TextWordWrap, text)
        # outline of the field's class
        if chosen in TEXTURE_POLYGONS:
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#111111"), 3))
            painter.drawPolygon(QtGui.QPolygonF(
                [self.point(s, c) for s, c in TEXTURE_POLYGONS[chosen]]))
        # axes: ticks and titles
        painter.setPen(_INK)
        for v in range(0, 101, 20):
            p = self.point(100 - v, v)                                   # left side: clay
            painter.drawText(QtCore.QPointF(p.x() - 26, p.y() + 4), str(v))
            p = self.point(v, 0)                                         # base: sand
            painter.drawText(QtCore.QPointF(p.x() - 8, p.y() + 16), str(v))
            p = self.point(0, 100 - v)                                   # right side: silt
            painter.drawText(QtCore.QPointF(p.x() + 6, p.y() + 4), str(v))
        bold = painter.font()
        bold.setBold(True)
        painter.setFont(bold)
        a, b = self.point(100, 0), self.point(0, 100)
        painter.drawText(QtCore.QPointF((a.x() + b.x()) / 2 - 70, (a.y() + b.y()) / 2),
                         tr("analysis.texture.axis_clay"))
        c = self.point(0, 0)
        painter.drawText(QtCore.QPointF((b.x() + c.x()) / 2 + 22, (b.y() + c.y()) / 2),
                         tr("analysis.texture.axis_silt"))
        painter.drawText(QtCore.QPointF((a.x() + c.x()) / 2 - 20, a.y() + 32),
                         tr("analysis.texture.axis_sand"))
        # the field's point
        f = self.figure
        if f.sand is not None and f.clay is not None:
            p = self.point(f.sand, f.clay)
            painter.setPen(QtGui.QPen(QtGui.QColor("white"), 3))
            painter.setBrush(QtGui.QColor("#111111"))
            painter.drawEllipse(p, 7, 7)
        painter.end()


# (object figure)
# the widget that draws a result's figure, or None for an unknown kind
def figure_widget(figure):
    from fieldshift.analysis.models import TextureFigure
    if isinstance(figure, TextureFigure):
        return TextureTriangle(figure)
    return None
