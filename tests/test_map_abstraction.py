"""Tests for the map abstraction layer (run without a display)."""

import math
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# never read or write the user's real saved fields
os.environ["FIELDSHIFT_FIELDS_DIR"] = tempfile.mkdtemp(prefix="fieldshift-test-")

from fieldshift.map import Event, LayerKind, LayerSpec, create_map_view  # noqa: E402
from fieldshift.qt import HAS_QGIS  # noqa: E402

from qt_app import get_app  # noqa: E402


def setUpModule():
    get_app()


class EventTest(unittest.TestCase):
    def test_emit_and_disconnect(self):
        seen = []
        event = Event()
        cb = event.connect(lambda *a: seen.append(a))
        event.emit(1, 2)
        event.disconnect(cb)
        event.emit(3, 4)
        self.assertEqual(seen, [(1, 2)])


class LayerSpecTest(unittest.TestCase):
    def test_constructors(self):
        self.assertIs(LayerSpec.xyz("osm", "u").kind, LayerKind.XYZ)
        self.assertIs(LayerSpec.vector("v", "a.geojson").kind, LayerKind.VECTOR)
        self.assertIs(LayerSpec.raster("r", "a.tif").kind, LayerKind.RASTER)


# small square near Santiago, (lon, lat)
SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


class _ViewContract:
    """Behaviour every MapView backend must have."""

    backend = None

    def setUp(self):
        self.view = create_map_view(self.backend)
        self.changes = 0
        self.view.layers_changed.connect(self._count)

    def _count(self):
        self.changes += 1

    def test_add_toggle_remove(self):
        self.assertIsNotNone(self.view.widget())
        layer_id = self.view.add_layer(self.make_spec("first"))
        self.assertEqual([i.id for i in self.view.layers()], [layer_id])
        self.view.set_layer_visible(layer_id, False)
        self.assertFalse(self.view.layers()[0].visible)
        self.view.remove_layer(layer_id)
        self.assertEqual(self.view.layers(), [])
        self.assertEqual(self.changes, 3)

    def test_top_layer_first(self):
        a = self.view.add_layer(self.make_spec("a"))
        b = self.view.add_layer(self.make_spec("b"))
        self.assertEqual([i.id for i in self.view.layers()], [b, a])

    def test_locked_option(self):
        spec = self.make_spec("base")
        locked = self.view.add_layer(LayerSpec(spec.name, spec.source, spec.kind,
                                               {**spec.options, "locked": True}))
        normal = self.view.add_layer(self.make_spec("mine"))
        self.view.set_layer_visible(locked, False)
        flags = {i.id: i.locked for i in self.view.layers()}
        self.assertEqual(flags, {locked: True, normal: False})

    def test_attribution_option(self):
        spec = self.make_spec("sat")
        credited = self.view.add_layer(LayerSpec(spec.name, spec.source, spec.kind,
                                                 {**spec.options, "attribution": "Credit"}))
        plain = self.view.add_layer(self.make_spec("mine"))
        credits = {i.id: i.attribution for i in self.view.layers()}
        self.assertEqual(credits, {credited: "Credit", plain: ""})

    def test_draw_polygon(self):
        drawn = []
        self.view.polygon_drawn.connect(drawn.append)
        self.assertFalse(self.view.is_drawing())
        self.view.start_polygon_drawing()
        self.assertTrue(self.view.is_drawing())
        self.close_polygon(SQUARE)
        self.assertFalse(self.view.is_drawing())
        self.assertEqual(len(drawn), 1)
        for (lon, lat), (elon, elat) in zip(drawn[0], SQUARE):
            self.assertAlmostEqual(lon, elon, places=6)
            self.assertAlmostEqual(lat, elat, places=6)

    def test_cancel_drawing(self):
        cancelled = []
        self.view.drawing_cancelled.connect(lambda: cancelled.append(True))
        self.view.cancel_drawing()                  # idle: nothing happens
        self.view.start_polygon_drawing()
        self.view.cancel_drawing()
        self.assertFalse(self.view.is_drawing())
        self.assertEqual(cancelled, [True])

    def test_double_click_on_a_layer(self):
        clicked = []
        self.view.layer_double_clicked.connect(lambda *a: clicked.append(a))
        layer_id = self.add_square_layer("field")
        self.double_click_square()
        self.assertEqual([c[0] for c in clicked], [layer_id])
        lon, lat = clicked[0][1:]
        self.assertTrue(-70.70 <= lon <= -70.69 and -33.41 <= lat <= -33.40)

    def test_double_click_ignores_locked_hidden_and_drawing(self):
        clicked = []
        self.view.layer_double_clicked.connect(lambda *a: clicked.append(a))
        locked = self.add_square_layer("base", locked=True)
        self.double_click_square()
        self.assertEqual(clicked, [])                       # locked
        layer_id = self.add_square_layer("field")
        self.view.set_layer_visible(layer_id, False)
        self.double_click_square()
        self.assertEqual(clicked, [])                       # hidden
        self.view.set_layer_visible(layer_id, True)
        self.view.start_polygon_drawing()
        self.double_click_square()
        self.assertEqual(clicked, [])                       # drawing
        self.view.cancel_drawing()
        self.double_click_square()
        self.assertEqual([c[0] for c in clicked], [layer_id])
        self.assertNotEqual(layer_id, locked)

    def test_view_changed_on_zoom(self):
        changes = []
        self.view.view_changed.connect(lambda: changes.append(1))
        self.view.zoom_to_extent(-70.72, -33.42, -70.67, -33.39)
        self.view.set_center(-70.70, -33.40)
        self.assertGreaterEqual(len(changes), 2)

    def test_meters_per_pixel_is_none_or_positive(self):
        value = self.view.meters_per_pixel()
        self.assertTrue(value is None or value > 0)

    def make_spec(self, name):
        return LayerSpec.vector(name, "Point?crs=EPSG:4326")

    # (list vertices)
    # closes the drawing in progress with these (lon, lat) vertices
    def close_polygon(self, vertices):
        raise NotImplementedError

    # (str name, **options)
    # adds a layer with the SQUARE polygon; returns its id
    def add_square_layer(self, name, **options):
        raise NotImplementedError

    # ()
    # double-clicks the middle of SQUARE on the map
    def double_click_square(self):
        raise NotImplementedError


class PlaceholderViewTest(_ViewContract, unittest.TestCase):
    backend = "placeholder"

    def test_no_scale_without_a_map(self):
        self.assertIsNone(self.view.meters_per_pixel())

    def add_square_layer(self, name, **options):
        self._square_id = self.view.add_layer(LayerSpec.vector(name, "square.geojson", **options))
        return self._square_id

    def double_click_square(self):
        self.view.simulate_double_click(self._square_id, -70.695, -33.405)

    def close_polygon(self, vertices):
        self.view.simulate_polygon(vertices)


@unittest.skipUnless(HAS_QGIS, "QGIS not installed")
class QgisViewTest(_ViewContract, unittest.TestCase):
    backend = "qgis"

    def make_spec(self, name):
        # in-memory vector layer: no file and no network needed
        return LayerSpec(name, "Point?crs=EPSG:4326", LayerKind.VECTOR,
                         {"provider": "memory"})

    def test_meters_per_pixel_matches_the_ground(self):
        self._pixels(SQUARE)                    # 800 px wide, about 0.05 deg of longitude
        canvas = self.view.canvas()
        extent = self.view._to_wgs.transformBoundingBox(canvas.extent())
        lat = math.radians(extent.center().y())
        expected = extent.width() * 111_195 * math.cos(lat) / canvas.width()
        self.assertAlmostEqual(self.view.meters_per_pixel() / expected, 1, delta=0.01)
        before = self.view.meters_per_pixel()
        self.view.set_center(-70.70, -33.40, scale=canvas.scale() / 4)    # zoom in x4
        self.assertAlmostEqual(before / self.view.meters_per_pixel(), 4, delta=0.1)

    def test_canvas_keeps_the_old_picture_while_redrawing(self):
        # regression: the satellite tiles vanished every time the map moved
        canvas = self.view.canvas()
        self.assertTrue(canvas.isParallelRenderingEnabled())
        self.assertTrue(canvas.isCachingEnabled())
        self.assertTrue(canvas.previewJobsEnabled())
        self.assertGreaterEqual(canvas.mapUpdateInterval(), 10_000)

    def test_invalid_source_raises(self):
        with self.assertRaises(ValueError):
            self.view.add_layer(LayerSpec.vector("bad", "/does/not/exist.geojson"))

    def test_label_option_turns_labels_on(self):
        spec = self.make_spec("labelled")
        plain = self.view.add_layer(spec)
        labelled = self.view.add_layer(LayerSpec(
            "labelled", spec.source, spec.kind,
            {**spec.options, "label_field": "name", "label_color": "#ffffff"}))
        project = self.view._project
        self.assertFalse(project.mapLayer(plain).labelsEnabled())
        layer = project.mapLayer(labelled)
        self.assertTrue(layer.labelsEnabled())
        settings = layer.labeling().settings()
        self.assertEqual(settings.fieldName, "name")
        # keep the QgsTextFormat copy alive: buffer() returns a reference into
        # it, and chaining on the temporary crashes under PyQt6 (QGIS 4)
        text_format = settings.format()
        self.assertTrue(text_format.buffer().enabled())                # halo
        self.assertEqual(text_format.color().name(), "#ffffff")

    def add_square_layer(self, name, **options):
        import json
        ring = [list(v) for v in SQUARE] + [list(SQUARE[0])]
        path = os.path.join(tempfile.mkdtemp(prefix="fieldshift-test-"), f"{name}.geojson")
        with open(path, "w") as fh:
            json.dump({"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {"name": name},
                "geometry": {"type": "Polygon", "coordinates": [ring]}}]}, fh)
        return self.view.add_layer(LayerSpec.vector(name, path, **options))

    def double_click_square(self):
        from fieldshift.qt import QtCore
        lon = sum(v[0] for v in SQUARE) / len(SQUARE)
        lat = sum(v[1] for v in SQUARE) / len(SQUARE)
        pos = self._pixels([(lon, lat)])[0]
        self.view.canvas().mapTool().canvasDoubleClickEvent(self._mouse(
            QtCore.QEvent.Type.MouseButtonDblClick, pos, QtCore.Qt.MouseButton.LeftButton))

    def test_click_does_not_recentre_but_drag_pans(self):
        from fieldshift.qt import QtCore
        Left, NoButton = QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton
        Type = QtCore.QEvent.Type
        self._pixels(SQUARE)
        canvas, tool = self.view.canvas(), self.view.canvas().mapTool()
        start = QtCore.QPointF(700, 100)
        before = canvas.center()
        tool.canvasPressEvent(self._mouse(Type.MouseButtonPress, start, Left))
        tool.canvasReleaseEvent(self._mouse(Type.MouseButtonRelease, start, Left))
        self.assertAlmostEqual(canvas.center().x(), before.x(), places=3)    # plain click
        self.assertAlmostEqual(canvas.center().y(), before.y(), places=3)
        end = QtCore.QPointF(500, 200)
        tool.canvasPressEvent(self._mouse(Type.MouseButtonPress, start, Left))
        tool.canvasMoveEvent(self._mouse(Type.MouseMove, end, NoButton, Left))
        tool.canvasReleaseEvent(self._mouse(Type.MouseButtonRelease, end, Left, NoButton))
        self.assertGreater(abs(canvas.center().x() - before.x()), 1)         # drag

    def test_double_click_on_empty_map_still_zooms_in(self):
        from fieldshift.qt import QtCore
        clicked = []
        self.view.layer_double_clicked.connect(lambda *a: clicked.append(a))
        self.add_square_layer("field")
        self.double_click_square()
        scale_after_hit = self.view.canvas().scale()
        self.view.zoom_to_extent(-70.72, -33.42, -70.67, -33.39)     # same view again
        scale = self.view.canvas().scale()
        self.assertAlmostEqual(scale_after_hit, scale, delta=scale * 0.001)   # hit: no zoom
        corner = self._pixels([(-70.719, -33.419)])[0]               # no field here
        self.view.canvas().mapTool().canvasDoubleClickEvent(self._mouse(
            QtCore.QEvent.Type.MouseButtonDblClick, corner, QtCore.Qt.MouseButton.LeftButton))
        self.assertEqual(len(clicked), 1)                            # only the first one
        self.assertLess(self.view.canvas().scale(), scale)           # empty: zoomed in

    def close_polygon(self, vertices):
        from qgis.core import QgsPointXY
        self._pixels(vertices)          # zoom in: vertices must be pixels apart
        tool = self.view.canvas().mapTool()
        for lon, lat in vertices:
            tool.add_vertex(self.view._to_map.transform(QgsPointXY(lon, lat)))
        self.assertTrue(tool.finish())

    # (list vertices)
    # shows the canvas zoomed on the square; returns the pixel of each vertex
    def _pixels(self, vertices):
        from qgis.core import QgsPointXY
        canvas = self.view.canvas()
        canvas.resize(800, 600)
        canvas.show()
        self.view.zoom_to_extent(-70.72, -33.42, -70.67, -33.39)
        to_pixel = canvas.getCoordinateTransform()
        return [to_pixel.transform(self.view._to_map.transform(QgsPointXY(lon, lat))).toQPointF()
                for lon, lat in vertices]

    def _mouse(self, kind, pos, button, buttons=None):
        from qgis.gui import QgsMapMouseEvent
        from fieldshift.qt import QtCore
        buttons = button if buttons is None else buttons
        return QgsMapMouseEvent(self.view.canvas(), kind, pos.toPoint(), button, buttons,
                                QtCore.Qt.KeyboardModifier.NoModifier)

    def _click(self, pos, button=None):
        from fieldshift.qt import QtCore
        button = button or QtCore.Qt.MouseButton.LeftButton
        self.view.canvas().mapTool().canvasReleaseEvent(
            self._mouse(QtCore.QEvent.Type.MouseButtonRelease, pos, button))

    def _key(self, key):
        from fieldshift.qt import QtCore, QtGui
        event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key,
                                QtCore.Qt.KeyboardModifier.NoModifier)
        self.view.canvas().mapTool().keyPressEvent(event)

    def _move(self, pos):
        from fieldshift.qt import QtCore
        self.view.canvas().mapTool().canvasMoveEvent(
            self._mouse(QtCore.QEvent.Type.MouseMove, pos, QtCore.Qt.MouseButton.NoButton))

    def test_first_vertex_grows_when_a_click_would_close(self):
        from fieldshift.qt import QtCore
        pixels = self._pixels(SQUARE)
        self.view.start_polygon_drawing()
        tool = self.view.canvas().mapTool()
        near_first = pixels[0] + QtCore.QPointF(4, 3)
        self._click(pixels[0])
        self._click(pixels[1])
        self._move(near_first)                      # only 2 vertices: no signal
        self.assertFalse(tool.closing())
        self.assertEqual(tool._close_marker.numberOfVertices(), 0)
        self._click(pixels[2])
        self._move(pixels[3])                       # far from the first vertex
        self.assertFalse(tool.closing())
        self._move(near_first)                      # inside CLOSE_TOLERANCE_PX
        self.assertTrue(tool.closing())
        self.assertEqual(tool._close_marker.numberOfVertices(), 1)
        self.assertGreater(tool._close_marker.iconSize(), tool._markers.iconSize())
        self._move(pixels[3])                       # leaves the zone: back to normal
        self.assertEqual(tool._close_marker.numberOfVertices(), 0)
        self._move(near_first)
        self._key(QtCore.Qt.Key.Key_Escape)         # ending the drawing clears it
        self.assertEqual(tool._close_marker.numberOfVertices(), 0)

    def test_clicks_close_on_first_vertex_and_go_back_to_pan(self):
        from qgis.gui import QgsMapToolPan
        drawn = []
        self.view.polygon_drawn.connect(drawn.append)
        pixels = self._pixels(SQUARE)
        self.view.start_polygon_drawing()
        for pos in pixels[:3]:
            self._click(pos)
        self._click(pixels[0])                      # click on the first vertex
        self.assertEqual(len(drawn), 1)
        self.assertEqual(len(drawn[0]), 3)
        self.assertAlmostEqual(drawn[0][1][0], SQUARE[1][0], places=4)
        self.assertIsInstance(self.view.canvas().mapTool(), QgsMapToolPan)

    def test_right_click_needs_three_vertices(self):
        from fieldshift.qt import QtCore
        drawn = []
        self.view.polygon_drawn.connect(drawn.append)
        pixels = self._pixels(SQUARE)
        self.view.start_polygon_drawing()
        self._click(pixels[0])
        self._click(pixels[1])
        self._click(pixels[2], QtCore.Qt.MouseButton.RightButton)   # only 2: ignored
        self.assertTrue(self.view.is_drawing())
        self._click(pixels[2])
        self._click(pixels[2])                      # same spot: not a new vertex
        self._click(pixels[3], QtCore.Qt.MouseButton.RightButton)
        self.assertEqual([len(v) for v in drawn], [3])

    def test_backspace_and_escape(self):
        from fieldshift.qt import QtCore
        cancelled = []
        self.view.drawing_cancelled.connect(lambda: cancelled.append(True))
        pixels = self._pixels(SQUARE)
        self.view.start_polygon_drawing()
        tool = self.view.canvas().mapTool()
        self._click(pixels[0])
        self._click(pixels[1])
        self._key(QtCore.Qt.Key.Key_Backspace)
        self.assertEqual(len(tool.points()), 1)
        self._key(QtCore.Qt.Key.Key_Escape)
        self.assertEqual(cancelled, [True])
        self.assertFalse(self.view.is_drawing())

    def test_switching_tool_cancels_drawing(self):
        cancelled = []
        self.view.drawing_cancelled.connect(lambda: cancelled.append(True))
        self.view.start_polygon_drawing()
        self.view.set_click_mode(True)
        self.assertEqual(cancelled, [True])
        self.assertIs(self.view.canvas().mapTool(), self.view._click_tool)


class MainWindowTest(unittest.TestCase):
    def test_map_left_panel_right(self):
        from fieldshift.ui import MainWindow, SidePanel
        view = create_map_view("placeholder")
        window = MainWindow(view)
        splitter = window.map_splitter
        self.assertIs(window.tabs.widget(0), splitter)          # the map is the first tab
        self.assertTrue(splitter.widget(0).isAncestorOf(view.widget()))
        self.assertTrue(splitter.widget(0).isAncestorOf(window.fields_bar))
        self.assertIsInstance(splitter.widget(1), SidePanel)
        view.add_layer(LayerSpec.xyz("osm", "https://example/{z}/{x}/{y}.png"))
        self.assertEqual(window.panel.layer_list.count(), 1)

    def test_attribution_shown_while_layer_is_visible(self):
        from fieldshift.ui import MainWindow
        view = create_map_view("placeholder")
        window = MainWindow(view)
        self.assertEqual(window.attribution_label.text(), "")
        sat = view.add_layer(LayerSpec.xyz("sat", "u", attribution="Imagery by X"))
        self.assertEqual(window.attribution_label.text(), "Imagery by X")
        view.set_layer_visible(sat, False)
        self.assertEqual(window.attribution_label.text(), "")


if __name__ == "__main__":
    unittest.main()
