"""Tests for the map abstraction layer (run without a display)."""

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

    def make_spec(self, name):
        return LayerSpec.vector(name, "Point?crs=EPSG:4326")

    # (list vertices)
    # closes the drawing in progress with these (lon, lat) vertices
    def close_polygon(self, vertices):
        raise NotImplementedError


class PlaceholderViewTest(_ViewContract, unittest.TestCase):
    backend = "placeholder"

    def close_polygon(self, vertices):
        self.view.simulate_polygon(vertices)


@unittest.skipUnless(HAS_QGIS, "QGIS not installed")
class QgisViewTest(_ViewContract, unittest.TestCase):
    backend = "qgis"

    def make_spec(self, name):
        # in-memory vector layer: no file and no network needed
        return LayerSpec(name, "Point?crs=EPSG:4326", LayerKind.VECTOR,
                         {"provider": "memory"})

    def test_invalid_source_raises(self):
        with self.assertRaises(ValueError):
            self.view.add_layer(LayerSpec.vector("bad", "/does/not/exist.geojson"))

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

    def _mouse(self, kind, pos, button):
        from qgis.gui import QgsMapMouseEvent
        return QgsMapMouseEvent(self.view.canvas(), kind, pos.toPoint(), button)

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
        splitter = window.centralWidget()
        self.assertTrue(splitter.widget(0).isAncestorOf(view.widget()))
        self.assertTrue(splitter.widget(0).isAncestorOf(window.fields_bar))
        self.assertIsInstance(splitter.widget(1), SidePanel)
        view.add_layer(LayerSpec.xyz("osm", "https://example/{z}/{x}/{y}.png"))
        self.assertEqual(window.panel.layer_list.count(), 1)


if __name__ == "__main__":
    unittest.main()
