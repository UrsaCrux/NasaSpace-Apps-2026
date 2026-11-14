"""QGIS map tool that lets the user draw one polygon. Used by QgisMapView."""

from qgis.core import Qgis
from qgis.gui import QgsMapTool, QgsRubberBand

from fieldshift.qt import QtCore, QtGui

# a click closer than this (pixels) to the first vertex closes the polygon
CLOSE_TOLERANCE_PX = 10
# a click closer than this (pixels) to the last vertex adds no new vertex
DUPLICATE_TOLERANCE_PX = 3
# fewest vertices of a polygon
MIN_VERTICES = 3

# preview colours: semi-transparent fill, solid outline
_FILL = QtGui.QColor(46, 125, 50, 70)
_STROKE = QtGui.QColor(27, 94, 32)

# size (pixels) of a vertex marker, and of the first one when a click would
# close the polygon; the closing marker is amber so it stands out
VERTEX_SIZE_PX = 8
CLOSE_VERTEX_SIZE_PX = 18
_CLOSE_COLOR = QtGui.QColor(255, 193, 7)

_Qt = QtCore.Qt


# map tool for drawing a polygon: left click adds a vertex, double click,
# right click or a click on the first vertex closes it, Backspace removes
# the last vertex, Esc cancels. a rubber band previews the polygon up to the
# cursor. points are in the canvas CRS
class PolygonDrawTool(QgsMapTool):

    # (QgsMapCanvas canvas, callable on_finished, callable on_cancelled)
    # on_finished gets the list of QgsPointXY vertices; on_cancelled no arguments
    def __init__(self, canvas, on_finished, on_cancelled):
        super().__init__(canvas)
        self._on_finished = on_finished
        self._on_cancelled = on_cancelled
        self._active = False
        self._points = []
        self._cursor = None

        self._band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._band.setFillColor(_FILL)
        self._band.setStrokeColor(_STROKE)
        self._band.setWidth(2)
        self._markers = QgsRubberBand(canvas, Qgis.GeometryType.Point)
        self._markers.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)
        self._markers.setIconSize(VERTEX_SIZE_PX)
        self._markers.setColor(_STROKE)
        # enlarged copy of the first vertex, shown while a click would close
        self._close_marker = QgsRubberBand(canvas, Qgis.GeometryType.Point)
        self._close_marker.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)
        self._close_marker.setIconSize(CLOSE_VERTEX_SIZE_PX)
        self._close_marker.setColor(_CLOSE_COLOR)
        self._close_marker.setSecondaryStrokeColor(_STROKE)
        self._close_marker.setWidth(3)
        self._set_cursor(_Qt.CursorShape.CrossCursor)

    # ()
    # begins a new, empty drawing
    def start(self):
        self._clear()
        self._active = True

    # ()
    # True between start() and the end of the drawing
    def is_active(self):
        return self._active

    # ()
    # True when a click at the cursor would close the polygon: at least
    # MIN_VERTICES vertices and the cursor within CLOSE_TOLERANCE_PX of the first
    def closing(self):
        return (self._active and self._cursor is not None
                and len(self._points) >= MIN_VERTICES
                and self._pixel_distance(self._cursor, self._points[0]) <= CLOSE_TOLERANCE_PX)

    # ()
    # vertices placed so far (QgsPointXY, canvas CRS)
    def points(self):
        return list(self._points)

    # (QgsPointXY point)
    # adds a vertex unless it is on top of the previous one
    def add_vertex(self, point):
        if not self._active:
            return
        if self._points and self._pixel_distance(point, self._points[-1]) < DUPLICATE_TOLERANCE_PX:
            return
        self._points.append(point)
        self._update_bands()

    # ()
    # removes the last vertex
    def undo_vertex(self):
        if self._points:
            self._points.pop()
            self._update_bands()

    # ()
    # closes the polygon and calls on_finished; returns False (and keeps
    # drawing) when there are fewer than MIN_VERTICES vertices
    def finish(self):
        if not self._active or len(self._points) < MIN_VERTICES:
            return False
        points = list(self._points)
        self._active = False
        self._clear()
        self._on_finished(points)
        return True

    # ()
    # abandons the drawing and calls on_cancelled; no-op when idle
    def cancel(self):
        if not self._active:
            return
        self._active = False
        self._clear()
        self._on_cancelled()

    # -- QgsMapTool events -------------------------------------------------

    def canvasMoveEvent(self, event):
        if self._active:
            self._cursor = event.mapPoint()
            self._update_bands()

    def canvasReleaseEvent(self, event):
        if not self._active:
            return
        if event.button() == _Qt.MouseButton.RightButton:
            self.finish()
        elif event.button() == _Qt.MouseButton.LeftButton:
            point = event.mapPoint()
            if (len(self._points) >= MIN_VERTICES
                    and self._pixel_distance(point, self._points[0]) <= CLOSE_TOLERANCE_PX):
                self.finish()
            else:
                self.add_vertex(point)

    def canvasDoubleClickEvent(self, event):
        # the first click of the double click already added the last vertex
        if self._active:
            self.finish()

    def keyPressEvent(self, event):
        if not self._active:
            event.ignore()
        elif event.key() == _Qt.Key.Key_Escape:
            self.cancel()
            event.accept()
        elif event.key() in (_Qt.Key.Key_Backspace, _Qt.Key.Key_Delete):
            self.undo_vertex()
            event.accept()
        else:
            event.ignore()

    # -- helpers -------------------------------------------------------------

    def _pixel_distance(self, a, b):
        pa, pb = self.toCanvasCoordinates(a), self.toCanvasCoordinates(b)
        return ((pa.x() - pb.x()) ** 2 + (pa.y() - pb.y()) ** 2) ** 0.5

    def _update_bands(self):
        preview = list(self._points)
        if self._cursor is not None and preview:
            preview.append(self._cursor)
        self._band.reset(Qgis.GeometryType.Polygon)
        for i, point in enumerate(preview):
            self._band.addPoint(point, i == len(preview) - 1)
        self._markers.reset(Qgis.GeometryType.Point)
        for i, point in enumerate(self._points):
            self._markers.addPoint(point, i == len(self._points) - 1)
        self._close_marker.reset(Qgis.GeometryType.Point)
        closing = self.closing()
        if closing:
            self._close_marker.addPoint(self._points[0])
        self._set_cursor(_Qt.CursorShape.PointingHandCursor if closing
                         else _Qt.CursorShape.CrossCursor)

    def _set_cursor(self, shape):
        cursor = QtGui.QCursor(shape)
        self.setCursor(cursor)
        self.canvas().setCursor(cursor)       # the tool is already active

    def _clear(self):
        self._points = []
        self._cursor = None
        self._band.reset(Qgis.GeometryType.Polygon)
        self._markers.reset(Qgis.GeometryType.Point)
        self._close_marker.reset(Qgis.GeometryType.Point)
        self._set_cursor(_Qt.CursorShape.CrossCursor)
