"""Tests for the card shown while the mouse is over a field."""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.map import LayerSpec, create_map_view  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


def setUpModule():
    get_app()


class HoverCardTest(unittest.TestCase):
    def setUp(self):
        from fieldshift.ui import MainWindow
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        i18n.set_language("en")
        self.view = create_map_view("placeholder")
        self.window = MainWindow(self.view)
        self.card = self.window.hover_card
        self.field = self.window.fields.add(
            "North", SQUARE, color="#ff0000",
            data={"elevation": {"value": 258, "source": "prefilled"}})

    def test_shows_the_field_and_highlights_it(self):
        self.assertTrue(self.card.isHidden())
        self.view.simulate_hover(self.field)
        self.assertFalse(self.card.isHidden())
        self.assertIn("North", self.card.title_label.text())
        info = self.card.info_label.text()
        self.assertIn(f"{self.window.fields.field(self.field).area_ha:.2f} ha", info)
        self.assertIn("Crop: not chosen", info)
        self.assertIn("258 m", info)
        self.assertEqual(self.view.highlighted(), [tuple(v) for v in
                                                   self.window.fields.field(self.field).vertices])
        self.view.simulate_hover(None)
        self.assertTrue(self.card.isHidden())
        self.assertIsNone(self.view.highlighted())

    def test_other_layers_show_no_card(self):
        other = self.view.add_layer(LayerSpec.vector("NDVI", "x.geojson"))
        self.view.simulate_hover(other)
        self.assertTrue(self.card.isHidden())
        self.assertIsNone(self.view.highlighted())

    def test_card_goes_away_when_the_field_is_deleted_or_drawing_starts(self):
        self.view.simulate_hover(self.field)
        self.window.fields.remove(self.field)
        self.assertTrue(self.card.isHidden())
        other = self.window.fields.add("B", SQUARE)
        self.view.simulate_hover(other)
        self.window.fields_bar.draw_button.click()
        self.assertTrue(self.card.isHidden())

    def test_lets_clicks_through(self):
        from fieldshift.qt import QtCore
        self.assertTrue(self.card.testAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents))


if __name__ == "__main__":
    unittest.main()
