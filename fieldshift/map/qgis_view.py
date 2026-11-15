"""MapView implemented with a QGIS map canvas."""

import math
from urllib.parse import quote

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsRubberBand

from fieldshift.map.layer import LayerInfo, LayerKind
from fieldshift.map.pick_tool import PickPanTool
from fieldshift.map.polygon_tool import PolygonDrawTool
from fieldshift.map.view import MapView
from fieldshift.qt import QtCore, QtGui

# CRS the public API speaks (longitude / latitude)
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
# CRS the canvas draws in (same as web tiles)
WEB_MERCATOR = QgsCoordinateReferenceSystem("EPSG:3857")
# a double click counts as "on a feature" within this many pixels of it
PICK_TOLERANCE_PX = 4
# how often (ms) the canvas may show a half-finished picture while it redraws.
# a very long time means: keep showing the previous picture until the new one
# is complete, so the satellite tiles never vanish while new ones download
MAP_UPDATE_INTERVAL_MS = 60_000
# mean Earth radius (metres) used to measure the scale
EARTH_RADIUS_M = 6_371_008.8
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
        self._attribution = {}     # layer id -> credit text

        canvas = QgsMapCanvas()
        canvas.setCanvasColor(QtGui.QColor("#dde6ea"))
        canvas.setDestinationCrs(WEB_MERCATOR)
        canvas.enableAntiAliasing(True)
        # same rendering set-up as QGIS desktop: layers drawn in parallel,
        # unchanged layers reused from a cache, the area around the view
        # rendered in advance (panning shows tiles at once), and no
        # half-drawn pictures (see MAP_UPDATE_INTERVAL_MS)
        canvas.setParallelRenderingEnabled(True)
        canvas.setCachingEnabled(True)
        canvas.setPreviewJobsEnabled(True)
        canvas.setMapUpdateInterval(MAP_UPDATE_INTERVAL_MS)
        self._canvas = canvas

        self._to_map = QgsCoordinateTransform(WGS84, WEB_MERCATOR, self._project)
        self._to_wgs = QgsCoordinateTransform(WEB_MERCATOR, WGS84, self._project)

        self._pan_tool = PickPanTool(canvas, self._on_double_click, self._on_hover)
        self._hovered = None              # layer id under the mouse
        self._highlight_vertices = None
        self._highlight_band = QgsRubberBand(canvas, Qgis.GeometryType.Polygon)
        self._highlight_band.setFillColor(QtGui.QColor(255, 255, 255, 40))
        self._highlight_band.setStrokeColor(QtGui.QColor("#ffeb3b"))
        self._highlight_band.setWidth(4)
        # the mouse leaving the map ends the hover
        self._leave_watcher = _LeaveWatcher(lambda: self._set_hovered(None, None), canvas)
        canvas.installEventFilter(self._leave_watcher)
        self._click_tool = QgsMapToolEmitPoint(canvas)
        self._click_tool.canvasClicked.connect(self._on_click)
        self._draw_tool = PolygonDrawTool(canvas, self._on_polygon_done,
                                          self._on_drawing_cancelled)
        canvas.setMapTool(self._pan_tool)
        canvas.mapToolSet.connect(self._on_map_tool_set)
        canvas.xyCoordinates.connect(self._on_move)
        canvas.extentsChanged.connect(self.view_changed.emit)

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
        _apply_labels(layer, spec.options)
        self._project.addMapLayer(layer, False)
        self._order.insert(0, layer.id())
        if spec.options.get("locked"):
            self._locked.add(layer.id())
        if spec.options.get("attribution"):
            self._attribution[layer.id()] = spec.options["attribution"]
        self._sync_canvas()
        self.layers_changed.emit()
        return layer.id()

    def remove_layer(self, layer_id):
        if layer_id not in self._order:
            return
        self._order.remove(layer_id)
        self._hidden.discard(layer_id)
        self._locked.discard(layer_id)
        self._attribution.pop(layer_id, None)
        self._sync_canvas()
        if layer_id == self._hovered:
            self._set_hovered(None, None)
        self._project.removeMapLayer(layer_id)
        self.layers_changed.emit()

    def layers(self):
        result = []
        for layer_id in self._order:
            layer = self._project.mapLayer(layer_id)
            if layer is not None:
                result.append(LayerInfo(layer_id, layer.name(), _kind_of(layer),
                                        layer_id not in self._hidden,
                                        layer_id in self._locked,
                                        self._attribution.get(layer_id, "")))
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
        if new_tool is not self._pan_tool:
            self._set_hovered(None, None)         # drawing or clicking: no hover
        if old_tool is self._draw_tool and new_tool is not self._draw_tool:
            self._draw_tool.cancel()

    # ()
    # pushes the visible layers, in order, to the canvas
    def _sync_canvas(self):
        visible = [self._project.mapLayer(i) for i in self._order if i not in self._hidden]
        self._canvas.setLayers([layer for layer in visible if layer is not None])
        self._canvas.refresh()

    # (QgsPointXY point)
    # double click while panning: reports the topmost visible, unlocked
    # vector feature under point (canvas CRS). True when there was one
    def _on_double_click(self, point):
        layer_id = self._layer_at(point)
        if layer_id is None:
            return False
        p = self._to_wgs.transform(point)
        self.layer_double_clicked.emit(layer_id, p.x(), p.y())
        return True

    # (QgsPointXY point)
    # id of the topmost visible, unlocked vector layer with a feature under
    # point (canvas CRS), within PICK_TOLERANCE_PX; None when there is none
    def _layer_at(self, point):
        tolerance = self._canvas.mapUnitsPerPixel() * PICK_TOLERANCE_PX
        box = QgsRectangle(point.x() - tolerance, point.y() - tolerance,
                           point.x() + tolerance, point.y() + tolerance)
        for layer_id in self._order:                      # top layer first
            layer = self._project.mapLayer(layer_id)
            if (layer_id in self._hidden or layer_id in self._locked
                    or not isinstance(layer, QgsVectorLayer)):
                continue
            to_layer = QgsCoordinateTransform(WEB_MERCATOR, layer.crs(), self._project)
            area = QgsGeometry.fromRect(to_layer.transformBoundingBox(box))
            features = layer.getFeatures(QgsFeatureRequest().setFilterRect(area.boundingBox()))
            try:
                hit = any(f.geometry().intersects(area) for f in features)
            finally:
                features.close()  # any() may stop early and leave the iterator open
            if hit:
                return layer_id
        return None

    # mouse moved while panning (point None: dragging)
    def _on_hover(self, point):
        self._set_hovered(self._layer_at(point) if point is not None else None, point)

    # emits layer_hovered when the layer under the mouse changes
    def _set_hovered(self, layer_id, point):
        if layer_id == self._hovered:
            return
        self._hovered = layer_id
        p = self._to_wgs.transform(point) if point is not None else QgsPointXY(0, 0)
        self.layer_hovered.emit(layer_id, p.x(), p.y())

    def set_highlight(self, vertices):
        # built from the vertices, not from the layer's features: reading a
        # layer's features for this and then removing the layer crashed QGIS
        # when the program exits
        self._highlight_band.reset(Qgis.GeometryType.Polygon)
        self._highlight_vertices = [tuple(v) for v in vertices] if vertices else None
        if not self._highlight_vertices:
            return
        last = len(self._highlight_vertices) - 1
        for i, (lon, lat) in enumerate(self._highlight_vertices):
            self._highlight_band.addPoint(self._to_map.transform(QgsPointXY(lon, lat)), i == last)

    def highlighted(self):
        return self._highlight_vertices

    def zoom_by(self, factor):
        self._canvas.zoomByFactor(factor)
        self._canvas.refresh()

    def meters_per_pixel(self):
        width = self._canvas.width()
        units_per_pixel = self._canvas.mapUnitsPerPixel()
        if width <= 0 or not units_per_pixel or math.isnan(units_per_pixel):
            return None
        # measure 100 pixels across the centre of the view on the ground
        center = self._canvas.center()
        half = 50 * units_per_pixel
        try:
            a = self._to_wgs.transform(QgsPointXY(center.x() - half, center.y()))
            b = self._to_wgs.transform(QgsPointXY(center.x() + half, center.y()))
        except Exception:                 # outside Web Mercator (beyond the poles)
            return None
        return _haversine_m(a.y(), a.x(), b.y(), b.x()) / 100

    def _on_move(self, point):
        p = self._to_wgs.transform(point)
        self.cursor_moved.emit(p.x(), p.y())

    def _on_click(self, point, _button):
        p = self._to_wgs.transform(point)
        self.clicked.emit(p.x(), p.y())


# Qt event filter that calls on_leave when the mouse leaves the widget. it
# belongs to that widget (parent), so Qt deletes it together with the map
class _LeaveWatcher(QtCore.QObject):

    def __init__(self, on_leave, parent):
        super().__init__(parent)
        self._on_leave = on_leave

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Leave:
            self._on_leave()
        return False


# (float lat1, float lon1, float lat2, float lon2)
# great-circle distance in metres between two points in degrees
def _haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


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


# (QgsMapLayer layer, dict options)
# shows the "label_field" attribute over each feature of a vector layer,
# with a halo so it can be read on top of satellite imagery
def _apply_labels(layer, options):
    field = options.get("label_field")
    if not field or not isinstance(layer, QgsVectorLayer):
        return
    text = QgsTextFormat()
    text.setSize(options.get("label_size", 11))
    text.setSizeUnit(Qgis.RenderUnit.Points)
    text.setColor(QtGui.QColor(options.get("label_color", "#ffffff")))
    font = text.font()
    font.setBold(True)
    text.setFont(font)
    halo = QgsTextBufferSettings()
    halo.setEnabled(True)
    halo.setSize(1.6)
    halo.setSizeUnit(Qgis.RenderUnit.Millimeters)
    halo.setColor(QtGui.QColor(options.get("label_halo_color", "#1b1b1b")))
    text.setBuffer(halo)

    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.placement = Qgis.LabelPlacement.Horizontal   # inside the polygon
    settings.centroidInside = True
    settings.displayAll = True                            # never drop a name
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()


# (QgsMapLayer layer)
# guesses the LayerKind of a loaded QGIS layer
def _kind_of(layer):
    if isinstance(layer, QgsVectorLayer):
        return LayerKind.VECTOR
    if layer.providerType() == "wms":
        return LayerKind.XYZ
    return LayerKind.RASTER
