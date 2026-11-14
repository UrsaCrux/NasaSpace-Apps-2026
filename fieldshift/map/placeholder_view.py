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
        pass

    def zoom_to_extent(self, xmin, ymin, xmax, ymax):
        pass

    def zoom_to_layer(self, layer_id):
        pass

    def refresh(self):
        pass

    def start_polygon_drawing(self):
        self._drawing = True

    def cancel_drawing(self):
        if self._drawing:
            self._drawing = False
            self.drawing_cancelled.emit()

    def is_drawing(self):
        return self._drawing

    # (list vertices)
    # ends the current drawing as if the user had closed this polygon of
    # (lon, lat) vertices; there is no map to click on, so tests use this
    def simulate_polygon(self, vertices):
        if self._drawing:
            self._drawing = False
            self.polygon_drawn.emit([(float(x), float(y)) for x, y in vertices])
