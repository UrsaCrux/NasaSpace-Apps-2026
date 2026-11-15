"""Tests for the buttons floating over the map."""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift.map import LayerSpec, create_map_view  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


def setUpModule():
    get_app()


class MapControlsTest(unittest.TestCase):
    def setUp(self):
        from fieldshift.ui import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.view = create_map_view("placeholder")
        self.streets = self.view.add_layer(LayerSpec.xyz("Streets", "u", locked=True))
        self.satellite = self.view.add_layer(LayerSpec.xyz("Satellite", "u", locked=True))
        self.window = MainWindow(self.view, basemaps={"satellite": self.satellite,
                                                      "streets": self.streets})
        self.controls = self.window.map_controls

    def test_zoom_buttons(self):
        with mock.patch.object(self.view, "zoom_by") as zoom:
            self.controls.zoom_in_button.click()
            self.controls.zoom_out_button.click()
        self.assertEqual([c.args[0] for c in zoom.call_args_list], [0.5, 2.0])

    def test_fit_all_fields(self):
        self.assertFalse(self.controls.fit_button.isEnabled())       # no fields yet
        self.window.fields.add("A", SQUARE)
        self.window.fields.add("B", [(-71.0, -33.7), (-70.99, -33.7), (-70.99, -33.71)])
        self.assertTrue(self.controls.fit_button.isEnabled())
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.controls.fit_button.click()
        xmin, ymin, xmax, ymax = zoom.call_args.args
        self.assertTrue(xmin < -71.0 and xmax > -70.69 and ymin < -33.71 and ymax > -33.40)

    def test_background_switch(self):
        self.assertEqual(self.controls.basemap(), "satellite")       # satellite first
        self.assertTrue(self.controls.satellite_button.isChecked())
        self.controls.streets_button.click()
        visible = {i.id: i.visible for i in self.view.layers()}
        self.assertEqual((visible[self.streets], visible[self.satellite]), (True, False))
        self.assertTrue(self.controls.streets_button.isChecked())
        self.assertFalse(self.controls.satellite_button.isChecked())
        self.controls.satellite_button.click()
        self.assertEqual(self.controls.basemap(), "satellite")

    def test_order_background_fields_zoom(self):
        c = self.controls
        c.adjustSize()
        tops = [c.satellite_button.y(), c.fit_button.y(), c.zoom_in_button.y(), c.zoom_out_button.y()]
        self.assertEqual(tops, sorted(tops))
        self.assertEqual(len(set(tops)), 4)

    def test_no_switch_without_both_backgrounds(self):
        from fieldshift.ui import MainWindow
        window = MainWindow(create_map_view("placeholder"))
        self.assertIsNone(window.map_controls.satellite_button)


if __name__ == "__main__":
    unittest.main()
