"""Tests for the scale bar drawn over the map."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift.map import Event  # noqa: E402
from fieldshift.qt import HAS_QGIS, QtWidgets  # noqa: E402
from fieldshift.ui.scale_bar import (  # noqa: E402
    MARGIN_PX, TARGET_WIDTH_PX, ScaleBar, format_length, nice_length)
from qt_app import get_app  # noqa: E402


def setUpModule():
    get_app()


class NiceLengthTest(unittest.TestCase):
    def test_round_lengths(self):
        cases = {120: 100, 99: 50, 260: 200, 1999: 1000, 4200: 2000, 7: 5, 0.3: 0.2, 1: 1}
        for meters, expected in cases.items():
            with self.subTest(meters=meters):
                self.assertAlmostEqual(nice_length(meters), expected)
        self.assertEqual(nice_length(0), 0)

    def test_labels(self):
        self.assertEqual(format_length(500), "500 m")
        self.assertEqual(format_length(2000), "2 km")
        self.assertEqual(format_length(0.5), "50 cm")


class _FakeView:
    """Just what ScaleBar needs from a MapView."""

    def __init__(self):
        self.view_changed = Event()
        self.mpp = None
        self._widget = QtWidgets.QWidget()
        self._widget.resize(800, 600)

    def widget(self):
        return self._widget

    def meters_per_pixel(self):
        return self.mpp


class ScaleBarTest(unittest.TestCase):
    def setUp(self):
        self.view = _FakeView()
        self.bar = ScaleBar(self.view)

    def test_hidden_when_the_map_has_no_scale(self):
        self.assertTrue(self.bar.isHidden())
        self.assertEqual(self.bar.label(), "")

    def test_follows_the_scale(self):
        self.view.mpp = 2.5                      # 120 px = 300 m -> bar of 200 m
        self.view.view_changed.emit()
        self.assertFalse(self.bar.isHidden())
        self.assertEqual(self.bar.label(), "200 m")
        self.assertEqual(self.bar.bar_width(), 80)
        self.view.mpp = 25                       # zoomed out: 120 px = 3 km -> 2 km
        self.view.view_changed.emit()
        self.assertEqual(self.bar.label(), "2 km")
        self.assertLessEqual(self.bar.bar_width(), TARGET_WIDTH_PX)
        self.assertGreaterEqual(self.bar.bar_width(), TARGET_WIDTH_PX // 2)

    def test_stays_in_the_bottom_left_corner_and_lets_clicks_through(self):
        from fieldshift.qt import QtCore
        self.view.mpp = 1.0
        self.view.view_changed.emit()
        self.view.widget().resize(1000, 700)
        get_app().processEvents()
        self.view.widget().show()
        get_app().processEvents()
        self.assertEqual(self.bar.x(), MARGIN_PX)
        self.assertEqual(self.bar.y() + self.bar.height(), 700 - MARGIN_PX)
        self.assertTrue(self.bar.testAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.view.widget().hide()


@unittest.skipUnless(HAS_QGIS, "QGIS not installed")
class ScaleBarOnRealMapTest(unittest.TestCase):
    def test_shows_a_real_length_and_changes_with_zoom(self):
        from fieldshift.map import create_map_view
        from fieldshift.ui import MainWindow
        view = create_map_view("qgis")
        window = MainWindow(view)
        window.resize(1200, 800)
        window.show()
        view.zoom_to_extent(-70.72, -33.42, -70.67, -33.39)     # a few km wide
        get_app().processEvents()
        bar = window.scale_bar
        self.assertFalse(bar.isHidden())
        shown = bar.length_m()
        self.assertTrue(100 <= shown <= 2000, shown)
        # the drawn bar really covers that distance on the ground
        self.assertAlmostEqual(bar.bar_width() * view.meters_per_pixel() / shown, 1, delta=0.02)
        view.set_center(-70.70, -33.40, scale=view.canvas().scale() / 10)
        get_app().processEvents()
        self.assertLess(bar.length_m(), shown)
        window.hide()


if __name__ == "__main__":
    unittest.main()
