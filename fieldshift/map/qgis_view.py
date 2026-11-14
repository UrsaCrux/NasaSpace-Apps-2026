"""MapView implemented with a QGIS map canvas."""

from urllib.parse import quote

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsMapToolPan

from fieldshift.map.layer import LayerInfo, LayerKind
from fieldshift.map.polygon_tool import PolygonDrawTool
from fieldshift.map.view import MapView
from fieldshift.qt import QtGui

# CRS the public API speaks (longitude / latitude)
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
# CRS the canvas draws in (same as web tiles)
WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
# initial extent in lon/lat (Web Mercator is undefined at the poles)
WORLD = QgsRectangle(-180, -85, 180, 85)


# MapView backed by QgsMapCanvas; layers are registered in QgsProject.instance()
class QgisMapView(MapView):

    # ()
    # creates the canvas in Web Mercator with pan as the default tool
    def __init__(self):
        super().__init__()
        self._project = QgsProject.instance()
        self._order = []           # layer ids, top layer first
        self._hidden = set()
        self._locked = set()       # ids of layers added with the "locked" option

        canvas = QgsMapCanvas()
        canvas.setCanvasColor(QtGui.QColor("#dde6ea"))
        canvas.setDestinationCrs(WEB_MERCATOR)
        canvas.enableAntiAliasing(True)
        self._canvas = canvas

        self._to_map = QgsCoordinateTransform(WGS84, WEB_MERCATOR, self._project)
        self._to_wgs = QgsCoordinateTransform(WEB_MERCATOR, WGS84, self._project)

        self._pan_tool = QgsMapToolPan(canvas)
        self._click_tool = QgsMapToolEmitPoint(canvas)
        self._click_tool.canvasClicked.connect(self._on_click)
        self._draw_tool = PolygonDrawTool(canvas, self._on_polygon_done,
                                          self._on_drawing_cancelled)
        canvas.setMapTool(self._pan_tool)
        canvas.mapToolSet.connect(self._on_map_tool_set)
        canvas.xyCoordinates.connect(self._on_move)

        # a new canvas has a null extent, and centring / zooming on a null
        # extent does nothing: start with the whole world
        canvas.setExtent(self._to_map.transformBoundingBox(WORLD))

    # ()
    # the underlying QgsMapCanvas, for code that needs QGIS-specific features
    def canvas(self):
        return self._canvas

    # (bool enabled)
    # switches between the pan tool and the click tool (emits `clicked`)
    def set_click_mode(self, enabled):
        self._canvas.setMapTool(self._click_tool if enabled else self._pan_tool)

    def widget(self):
        return self._canvas

    def add_layer(self, spec):
        layer = _build_qgs_layer(spec)
        if not layer.isValid():
            raise ValueError(f"cannot open layer {spec.name!r} from {spec.source!r}")
        _apply_style(layer, spec.options)
        self._project.addMapLayer(layer, False)
        self._order.insert(0, layer.id())
        if spec.options.get("locked"):
            self._locked.add(layer.id())
        self._sync_canvas()
        self.layers_changed.emit()
        return layer.id()

    def remove_layer(self, layer_id):
        if layer_id not in self._order:
            return
        self._order.remove(layer_id)
        self._hidden.discard(layer_id)
        self._locked.discard(layer_id)
        self._sync_canvas()
        self._project.removeMapLayer(layer_id)
        self.layers_changed.emit()

    def layers(self):
        result = []
        for layer_id in self._order:
            layer = self._project.mapLayer(layer_id)
            if layer is not None:
                result.append(LayerInfo(layer_id, layer.name(), _kind_of(layer),
                                        layer_id not in self._hidden,
                                        layer_id in self._locked))
        return result

    def set_layer_visible(self, layer_id, visible):
        if layer_id not in self._order:
            return
        if visible:
            self._hidden.discard(layer_id)
        else:
            self._hidden.add(layer_id)
        self._sync_canvas()
        self.layers_changed.emit()

    def set_center(self, lon, lat, scale=None):
        self._canvas.setCenter(self._to_map.transform(QgsPointXY(lon, lat)))
        if scale is not None:
            self._canvas.zoomScale(scale)
        self._canvas.refresh()

    def zoom_to_extent(self, xmin, ymin, xmax, ymax):
        rect = self._to_map.transformBoundingBox(QgsRectangle(xmin, ymin, xmax, ymax))
        self._canvas.setExtent(rect)
        self._canvas.refresh()

    def zoom_to_layer(self, layer_id):
        layer = self._project.mapLayer(layer_id)
        if layer is None:
            return
        transform = QgsCoordinateTransform(layer.crs(), WEB_MERCATOR, self._project)
        self._canvas.setExtent(transform.transformBoundingBox(layer.extent()))
        self._canvas.refresh()

    def refresh(self):
        self._canvas.refresh()

    def start_polygon_drawing(self):
        if self._draw_tool.is_active():
            return
        self._draw_tool.start()
        self._canvas.setMapTool(self._draw_tool)
        self._canvas.setFocus()       # so Esc and Backspace reach the tool

    def cancel_drawing(self):
        self._draw_tool.cancel()

    def is_drawing(self):
        return self._draw_tool.is_active()

    # (list points)
    # the draw tool closed a polygon: back to panning, emit lon/lat vertices
    def _on_polygon_done(self, points):
        self._restore_pan()
        vertices = []
        for point in points:
            p = self._to_wgs.transform(point)
            vertices.append((p.x(), p.y()))
        self.polygon_drawn.emit(vertices)

    def _on_drawing_cancelled(self):
        self._restore_pan()
        self.drawing_cancelled.emit()

    def _restore_pan(self):
        if self._canvas.mapTool() is self._draw_tool:
            self._canvas.setMapTool(self._pan_tool)

    # another tool replaced the draw tool (e.g. set_click_mode): drop the drawing
    def _on_map_tool_set(self, new_tool, old_tool):
        if old_tool is self._draw_tool and new_tool is not self._draw_tool:
            self._draw_tool.cancel()

    # ()
    # pushes the visible layers, in order, to the canvas
    def _sync_canvas(self):
        visible = [self._project.mapLayer(i) for i in self._order if i not in self._hidden]
        self._canvas.setLayers([layer for layer in visible if layer is not None])
        self._canvas.refresh()

    def _on_move(self, point):
        p = self._to_wgs.transform(point)
        self.cursor_moved.emit(p.x(), p.y())

    def _on_click(self, point, _button):
        p = self._to_wgs.transform(point)
        self.clicked.emit(p.x(), p.y())


# (LayerSpec spec)
# turns a LayerSpec into an (unchecked) QgsMapLayer
def _build_qgs_layer(spec):
    if spec.kind is LayerKind.XYZ:
        zmin = spec.options.get("zmin", 0)
        zmax = spec.options.get("zmax", 19)
        uri = f"type=xyz&url={quote(spec.source, safe=':/')}&zmin={zmin}&zmax={zmax}"
        return QgsRasterLayer(uri, spec.name, "wms")
    if spec.kind is LayerKind.VECTOR:
        return QgsVectorLayer(spec.source, spec.name, spec.options.get("provider", "ogr"))
    if spec.kind is LayerKind.RASTER:
        return QgsRasterLayer(spec.source, spec.name, spec.options.get("provider", "gdal"))
    raise ValueError(f"unsupported layer kind: {spec.kind}")


# (QgsMapLayer layer, dict options)
# applies "fill_color" / "stroke_color" / "stroke_width" options to a polygon
# or point layer
def _apply_style(layer, options):
    if not isinstance(layer, QgsVectorLayer):
        return
    fill, stroke = options.get("fill_color"), options.get("stroke_color")
    width = options.get("stroke_width")
    if not (fill or stroke or width):
        return
    symbol = layer.renderer().symbol() if hasattr(layer.renderer(), "symbol") else None
    if symbol is None:
        return
    if fill:
        symbol.setColor(QtGui.QColor(fill))
    if stroke and symbol.symbolLayerCount():
        symbol_layer = symbol.symbolLayer(0)
        if hasattr(symbol_layer, "setStrokeColor"):
            symbol_layer.setStrokeColor(QtGui.QColor(stroke))
    if width and symbol.symbolLayerCount():
        symbol_layer = symbol.symbolLayer(0)
        if hasattr(symbol_layer, "setStrokeWidth"):
            symbol_layer.setStrokeWidth(float(width))
    layer.triggerRepaint()


# (QgsMapLayer layer)
# guesses the LayerKind of a loaded QGIS layer
def _kind_of(layer):
    if isinstance(layer, QgsVectorLayer):
        return LayerKind.VECTOR
    if layer.providerType() == "wms":
        return LayerKind.XYZ
    return LayerKind.RASTER
