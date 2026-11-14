"""Tests for the map abstraction layer (run without a display)."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift.map import Event, LayerKind, LayerSpec, create_map_view  # noqa: E402
from fieldshift.qt import HAS_QGIS, QtWidgets  # noqa: E402

_app = None


def setUpModule():
    global _app
    if HAS_QGIS:
        from qgis.core import QgsApplication
        _app = QgsApplication([], False)
        _app.initQgis()
    else:
        _app = QtWidgets.QApplication([])


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

    def make_spec(self, name):
        return LayerSpec.vector(name, "Point?crs=EPSG:4326")


class PlaceholderViewTest(_ViewContract, unittest.TestCase):
    backend = "placeholder"


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


class MainWindowTest(unittest.TestCase):
    def test_map_left_panel_right(self):
        from fieldshift.ui import MainWindow, SidePanel
        view = create_map_view("placeholder")
        window = MainWindow(view)
        splitter = window.centralWidget()
        self.assertIs(splitter.widget(0), view.widget())
        self.assertIsInstance(splitter.widget(1), SidePanel)
        view.add_layer(LayerSpec.xyz("osm", "https://example/{z}/{x}/{y}.png"))
        self.assertEqual(window.panel.layer_list.count(), 1)


if __name__ == "__main__":
    unittest.main()
