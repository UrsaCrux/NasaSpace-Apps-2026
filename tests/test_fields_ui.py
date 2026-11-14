"""Tests for the fields box and the layer list, with the placeholder map."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.fields import FieldStore  # noqa: E402
from fieldshift.map import LayerSpec, create_map_view  # noqa: E402
from fieldshift.qt import QtWidgets  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


def setUpModule():
    get_app()


class FieldsPanelTest(unittest.TestCase):
    def setUp(self):
        from fieldshift.ui import SidePanel
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "fields"
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": str(self.folder)})
        env.start()
        self.addCleanup(env.stop)
        i18n.set_language("en")
        self.view = create_map_view("placeholder")
        self.base = self.view.add_layer(LayerSpec.xyz("OpenStreetMap", "u", locked=True))
        self.panel = SidePanel(self.view)
        self.box = self.panel.fields_box

    def tearDown(self):
        self._tmp.cleanup()

    def labels(self):
        lst = self.panel.layer_list
        return [lst.item(i).text() for i in range(lst.count())]

    def select(self, layer_id):
        lst = self.panel.layer_list
        for i in range(lst.count()):
            if lst.item(i).data(0x0100) == layer_id:       # Qt.ItemDataRole.UserRole
                lst.setCurrentRow(i)
                return lst.item(i)
        self.fail(f"layer {layer_id} not in the list")

    def draw(self, name):
        self.box.draw_button.click()
        with mock.patch.object(self.box, "_ask_name", return_value=name):
            self.view.simulate_polygon(SQUARE)
        return next((i for i, f in self.box._fields.items() if f.name == name), None)

    def test_draw_button_toggles_drawing(self):
        self.box.draw_button.click()
        self.assertTrue(self.view.is_drawing())
        self.assertTrue(self.box.draw_button.isChecked())
        self.assertEqual(self.box.draw_button.text(), i18n.tr("fields.drawing"))
        self.box.draw_button.click()                       # second click cancels
        self.assertFalse(self.view.is_drawing())
        self.assertFalse(self.box.draw_button.isChecked())

    def test_save_drawn_field(self):
        self.assertFalse(self.box.export_button.isEnabled())
        layer_id = self.draw("North plot")
        self.assertIsNotNone(layer_id)
        self.assertFalse(self.box.draw_button.isChecked())
        self.assertTrue((self.folder / "North plot.geojson").is_file())
        self.assertIn("North plot  [field]", self.labels())
        self.assertTrue(self.box.export_button.isEnabled())

    def test_cancelled_name_discards_the_drawing(self):
        self.assertIsNone(self.draw(None))
        self.assertEqual(FieldStore(self.folder).fields(), [])
        self.assertEqual(len(self.labels()), 1)

    def test_click_on_field_zooms_with_margin(self):
        layer_id = self.draw("A")
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.panel._on_item_clicked(self.select(layer_id))
        xmin, ymin, xmax, ymax = zoom.call_args.args
        self.assertLess(xmin, -70.70)
        self.assertGreater(ymax, -33.40)

    def test_remove_field_asks_and_deletes_file(self):
        layer_id = self.draw("A")
        self.select(layer_id)
        with mock.patch.object(self.box, "_confirm_remove", return_value=False):
            self.panel._remove_selected()
        self.assertTrue(self.box.is_field(layer_id))
        self.select(layer_id)
        with mock.patch.object(self.box, "_confirm_remove", return_value=True):
            self.panel._remove_selected()
        self.assertFalse(self.box.is_field(layer_id))
        self.assertNotIn(layer_id, [i.id for i in self.view.layers()])
        self.assertEqual(list(self.folder.glob("*.geojson")), [])

    def test_base_layers_cannot_be_removed(self):
        self.assertEqual(self.labels(), ["🔒 OpenStreetMap  [xyz]"])
        self.select(self.base)
        with mock.patch.object(QtWidgets.QMessageBox, "information") as info:
            self.panel._remove_selected()
        info.assert_called_once()
        self.assertEqual([i.id for i in self.view.layers()], [self.base])

    def test_user_layers_are_removed_as_before(self):
        mine = self.view.add_layer(LayerSpec.vector("mine", "x.geojson"))
        self.select(mine)
        self.panel._remove_selected()
        self.assertEqual([i.id for i in self.view.layers()], [self.base])

    def test_saved_fields_are_loaded_at_start(self):
        from fieldshift.ui import SidePanel
        FieldStore(self.folder).create("Old field", SQUARE)
        panel = SidePanel(create_map_view("placeholder"))
        self.assertEqual(panel.layer_list.item(0).text(), "Old field  [field]")

    def test_export(self):
        self.draw("A")
        self.draw("B")
        out = Path(self._tmp.name) / "out.geojson"
        self.assertEqual(self.box.export_fields(out), 2)
        names = [f["properties"]["name"] for f in json.loads(out.read_text("utf-8"))["features"]]
        self.assertEqual(names, ["A", "B"])


class FieldNameDialogTest(unittest.TestCase):
    def test_suggestion_and_validation(self):
        from fieldshift.ui.fields_box import FieldNameDialog
        i18n.set_language("es")
        self.addCleanup(i18n.set_language, "en")
        with tempfile.TemporaryDirectory() as tmp:
            store = FieldStore(tmp)
            store.create("Terreno 1", SQUARE)
            dialog = FieldNameDialog(store)
            self.assertEqual(dialog.name(), "Terreno 2")
            self.assertTrue(dialog.save_button.isEnabled())
            dialog.name_edit.setText("terreno 1")
            self.assertFalse(dialog.save_button.isEnabled())
            self.assertIn("Ya existe", dialog.error_label.text())
            dialog.name_edit.setText("   ")
            self.assertFalse(dialog.save_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
