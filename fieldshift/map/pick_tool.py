"""QGIS pan tool that also reports a double click on a feature."""

from qgis.gui import QgsMapToolPan

from fieldshift.qt import QtCore, QtGui


# the default map tool: drag to pan, wheel to zoom. a double click first asks
# on_double_click whether a feature is under the cursor; only when nobody
# claims the click does it zoom in as the plain pan tool does. unlike the
# plain pan tool, a click without dragging does not recentre the map: the map
# would jump away under the cursor while the user double-clicks a field
class PickPanTool(QgsMapToolPan):

    # (QgsMapCanvas canvas, callable on_double_click, callable on_hover = None)
    # on_double_click gets the clicked QgsPointXY (canvas CRS) and returns True
    # when it used the click; on_hover gets the point under the mouse, or
    # None while the map is being dragged
    def __init__(self, canvas, on_double_click, on_hover=None):
        super().__init__(canvas)
        self._on_double_click = on_double_click
        self._on_hover = on_hover
        self._moved = False         # the mouse moved with the button held

    def canvasPressEvent(self, event):
        self._moved = False
        super().canvasPressEvent(event)

    def canvasMoveEvent(self, event):
        dragging = bool(event.buttons() & QtCore.Qt.MouseButton.LeftButton)
        if dragging:
            self._moved = True
        if self._on_hover is not None:
            self._on_hover(None if dragging else event.mapPoint())
        super().canvasMoveEvent(event)

    def canvasReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and not self._moved:
            # plain click: the base class would recentre here; only undo the
            # closed-hand cursor it set on press
            self.canvas().setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.OpenHandCursor))
            return
        super().canvasReleaseEvent(event)

    def canvasDoubleClickEvent(self, event):
        if self._on_double_click(event.mapPoint()):
            event.accept()
        else:
            super().canvasDoubleClickEvent(event)
