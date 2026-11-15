"""MapView used when QGIS is not installed. Keeps layers in memory only."""

import itertools
from dataclasses import replace

from fieldshift.map.layer import LayerInfo
from fieldshift.map.view import MapView
import sys

from fieldshift.qt import QGIS_IMPORT_ERROR, QtCore, QtWidgets


# MapView without a map engine: lets the panel and window be developed and
# tested on machines without QGIS
class PlaceholderMapView(MapView):

    # ()
    # creates an empty in-memory view
    def __init__(self):
        super().__init__()
        self._widget = None
        self._layers = {}          # id -> LayerInfo, insertion order = bottom first
        self._ids = itertools.count(1)
        self._drawing = False
        self._highlight = None
        self._marked = []
        self._center = None        # last set_center, so the UI can be tested

    def widget(self):
        if self._widget is None:
            label = QtWidgets.QLabel(
                "QGIS could not be imported by this Python:\n"
                f"{sys.executable} (Python {sys.version.split()[0]})\n\n"
                f"{QGIS_IMPORT_ERROR or 'backend forced to placeholder'}\n\n"
                "See docs/README.md, section 'QGIS is not found'."
            )
            label.setWordWrap(True)
            label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background:#dde6ea; color:#333; font-size:14px;")
            self._widget = label
        return self._widget

    def add_layer(self, spec):
        layer_id = f"layer{next(self._ids)}"
        self._layers[layer_id] = LayerInfo(layer_id, spec.name, spec.kind, True,
                                           bool(spec.options.get("locked")),
                                           spec.options.get("attribution", ""))
        self.layers_changed.emit()
        return layer_id

    def remove_layer(self, layer_id):
        if self._layers.pop(layer_id, None) is not None:
            self.layers_changed.emit()

    def layers(self):
        return list(reversed(self._layers.values()))

    def set_layer_visible(self, layer_id, visible):
        info = self._layers.get(layer_id)
        if info is not None and info.visible != visible:
            self._layers[layer_id] = replace(info, visible=visible)
            self.layers_changed.emit()

    def set_center(self, lon, lat, scale=None):
        self._center = (float(lon), float(lat))
        self.view_changed.emit()

    def zoom_to_extent(self, xmin, ymin, xmax, ymax):
        self.view_changed.emit()

    def zoom_to_layer(self, layer_id):
        if layer_id in self._layers:
            self.view_changed.emit()

    def set_highlight(self, vertices):
        self._highlight = [tuple(v) for v in vertices] if vertices else None

    def highlighted(self):
        return self._highlight

    def set_marked(self, polygons):
        self._marked = [[tuple(v) for v in polygon] for polygon in polygons or []]

    def marked(self):
        return [list(polygon) for polygon in self._marked]

    # (str layer_id, float lon = 0, float lat = 0)
    # reports a right click on a feature of this layer, as the real map would;
    # ignored for unknown, locked or hidden layers and while drawing
    def simulate_right_click(self, layer_id, lon=0.0, lat=0.0):
        info = self._layers.get(layer_id)
        if info is not None and info.visible and not info.locked and not self._drawing:
            self.layer_right_clicked.emit(layer_id, lon, lat)

    # (str layer_id or None, float lon = 0, float lat = 0)
    # reports the mouse entering a feature of this layer (None: leaving), as
    # the real map would; ignored for locked or hidden layers and while drawing
    def simulate_hover(self, layer_id, lon=0.0, lat=0.0):
        info = self._layers.get(layer_id) if layer_id is not None else None
        if layer_id is not None and (info is None or not info.visible or info.locked
                                     or self._drawing):
            return
        self.layer_hovered.emit(layer_id, lon, lat)

    def zoom_by(self, factor):
        self.view_changed.emit()

    def center(self):
        return self._center

    def meters_per_pixel(self):
        return None                 # no map, no scale

    def refresh(self):
        pass

    def start_polygon_drawing(self):
        self._drawing = True
        self.layer_hovered.emit(None, 0.0, 0.0)

    def cancel_drawing(self):
        if self._drawing:
            self._drawing = False
            self.drawing_cancelled.emit()

    def is_drawing(self):
        return self._drawing

    # (str layer_id, float lon = 0, float lat = 0)
    # reports a double click on a feature of this layer, as the real map
    # would; nothing happens for unknown, locked or hidden layers, or while
    # drawing
    def simulate_double_click(self, layer_id, lon=0.0, lat=0.0):
        info = self._layers.get(layer_id)
        if info is not None and info.visible and not info.locked and not self._drawing:
            self.layer_double_clicked.emit(layer_id, lon, lat)

    # (list vertices)
    # ends the current drawing as if the user had closed this polygon of
    # (lon, lat) vertices; there is no map to click on, so tests use this
    def simulate_polygon(self, vertices):
        if self._drawing:
            self._drawing = False
            self.polygon_drawn.emit([(float(x), float(y)) for x, y in vertices])
