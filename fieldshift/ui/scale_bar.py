"""Scale bar drawn over the bottom-left corner of the map.

Uses the map only through MapView: meters_per_pixel() for the size and the
view_changed event to follow pans and zooms. Hidden when the map cannot tell
its scale (placeholder map).
"""

import math

from fieldshift.qt import QtCore, QtGui, QtWidgets

# the bar is never wider than this (pixels); it is at least half of it
TARGET_WIDTH_PX = 120
# distance (pixels) from the bottom-left corner of the map
MARGIN_PX = 12
# inner padding, bar thickness and height of the whole box (pixels)
_PAD = 8
_BAR_HEIGHT = 6
_BOX_HEIGHT = 36

_BACKGROUND = QtGui.QColor(255, 255, 255, 215)
_INK = QtGui.QColor("#1b1b1b")
_PAPER = QtGui.QColor("#ffffff")


# (float meters)
# largest round length (1, 2 or 5 x 10^n metres) that is not longer than meters
def nice_length(meters):
    if meters <= 0:
        return 0.0
    power = 10.0 ** math.floor(math.log10(meters))
    for step in (5, 2, 1):
        if step * power <= meters * (1 + 1e-9):
            return step * power
    return power


# (float meters)
# length as people write it: "500 m", "2 km", "50 cm"
def format_length(meters):
    if meters >= 1000:
        return f"{meters / 1000:g} km"
    if meters >= 1:
        return f"{meters:g} m"
    return f"{meters * 100:g} cm"


# black and white bar with its length ("0 ... 200 m") over the map, in the
# bottom-left corner. mouse clicks go through it to the map
class ScaleBar(QtWidgets.QWidget):

    # (MapView view)
    # puts the bar on top of view.widget() and follows the view
    def __init__(self, view):
        super().__init__(view.widget())
        self.view = view
        self._length_m = 0.0
        self._bar_px = 0
        self._label = ""
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        font = self.font()
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1))
        font.setBold(True)
        self.setFont(font)
        view.widget().installEventFilter(self)
        view.view_changed.connect(self.refresh)
        self.refresh()

    # ()
    # the length shown, in metres (0 when hidden)
    def length_m(self):
        return self._length_m

    # ()
    # the text shown at the end of the bar ("200 m")
    def label(self):
        return self._label

    # ()
    # how wide the bar is drawn, in pixels
    def bar_width(self):
        return self._bar_px

    # ()
    # recomputes the bar from the current scale of the map
    def refresh(self):
        mpp = self.view.meters_per_pixel()
        if not mpp:
            self._length_m, self._bar_px, self._label = 0.0, 0, ""
            self.hide()
            return
        self._length_m = nice_length(mpp * TARGET_WIDTH_PX)
        self._bar_px = max(1, round(self._length_m / mpp))
        self._label = format_length(self._length_m)
        text_px = self.fontMetrics().horizontalAdvance(self._label)
        self.resize(max(self._bar_px, text_px) + 2 * _PAD + text_px // 2, _BOX_HEIGHT)
        self._place()
        self.show()
        self.raise_()
        self.update()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QtCore.QEvent.Type.Resize:
            self.refresh()
        return False

    def _place(self):
        parent = self.parentWidget()
        self.move(MARGIN_PX, parent.height() - self.height() - MARGIN_PX)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(_BACKGROUND)
        painter.drawRoundedRect(QtCore.QRectF(self.rect()), 6, 6)

        left = _PAD
        top = self.height() - _PAD - _BAR_HEIGHT
        half = self._bar_px / 2
        painter.setPen(QtGui.QPen(_INK, 1))
        painter.setBrush(_INK)
        painter.drawRect(QtCore.QRectF(left, top, half, _BAR_HEIGHT))
        painter.setBrush(_PAPER)
        painter.drawRect(QtCore.QRectF(left + half, top, self._bar_px - half, _BAR_HEIGHT))

        painter.setPen(_INK)
        metrics = self.fontMetrics()
        baseline = top - 4
        painter.drawText(QtCore.QPointF(left, baseline), "0")
        end = left + self._bar_px - metrics.horizontalAdvance(self._label) / 2
        painter.drawText(QtCore.QPointF(max(left + metrics.horizontalAdvance("0 "), end), baseline),
                         self._label)
        painter.end()
