"""Tests for fields in the window (bar under the map, side panel list),
with the placeholder map."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.fields import FieldStore  # noqa: E402
from fieldshift.fields.manager import FieldsManager  # noqa: E402
from fieldshift.map import LayerSpec, create_map_view  # noqa: E402
from fieldshift.qt import HAS_QGIS, QtCore  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


def setUpModule():
    get_app()


class _TempFields(unittest.TestCase):
    """Each test gets an empty fields folder and English texts."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name) / "fields"
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": str(self.folder)})
        env.start()
        self.addCleanup(env.stop)
        i18n.set_language("en")


class FieldsManagerTest(_TempFields):
    def setUp(self):
        super().setUp()
        self.view = create_map_view("placeholder")
        self.fields = FieldsManager(self.view)

    def test_add_shows_layer_and_saves_file(self):
        changes = []
        self.fields.fields_changed.connect(lambda: changes.append(1))
        layer_id = self.fields.add("A", SQUARE)
        self.assertTrue(self.fields.is_field(layer_id))
        self.assertEqual(self.fields.field(layer_id).name, "A")
        self.assertEqual([i.name for i in self.view.layers()], ["A"])
        self.assertTrue((self.folder / "A.geojson").is_file())
        self.assertEqual(changes, [1])

    def test_each_field_asks_for_its_name_as_label(self):
        specs = []
        original = self.view.add_layer
        self.view.add_layer = lambda spec: (specs.append(spec), original(spec))[1]
        self.fields.add("A", SQUARE)
        self.assertEqual(specs[0].options["label_field"], "name")

    def test_remove(self):
        layer_id = self.fields.add("A", SQUARE)
        self.assertTrue(self.fields.remove(layer_id))
        self.assertEqual(self.view.layers(), [])
        self.assertEqual(list(self.folder.glob("*")), [])
        self.assertFalse(self.fields.remove(layer_id))

    def test_layer_that_cannot_load_leaves_no_file(self):
        with mock.patch.object(self.view, "add_layer", side_effect=ValueError("bad")):
            with self.assertRaises(ValueError):
                self.fields.add("A", SQUARE)
        self.assertEqual(FieldStore(self.folder).fields(), [])

    def test_zoom_with_margin(self):
        layer_id = self.fields.add("A", SQUARE)
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.fields.zoom_to(layer_id)
        xmin, ymin, xmax, ymax = zoom.call_args.args
        self.assertLess(xmin, -70.70)
        self.assertGreater(ymax, -33.40)

    def test_selection(self):
        changes = []
        self.fields.selection_changed.connect(lambda: changes.append(1))
        a = self.fields.add("A", SQUARE)
        b = self.fields.add("B", SQUARE)
        self.fields.set_selected(b, True)
        self.fields.set_selected(a, True)
        self.fields.set_selected(a, True)                  # no change, no event
        self.assertEqual(self.fields.selected(), [a, b])   # oldest first
        self.fields.remove(a)
        self.assertEqual(self.fields.selected(), [b])
        self.assertEqual(len(changes), 3)

    def test_export_only_some(self):
        self.fields.add("A", SQUARE)
        b = self.fields.add("B", SQUARE)
        out = Path(self._tmp.name) / "some.geojson"
        self.assertEqual(self.fields.export(out, [b]), 1)
        names = [f["properties"]["name"] for f in json.loads(out.read_text("utf-8"))["features"]]
        self.assertEqual(names, ["B"])

    def test_saved_fields_are_loaded(self):
        FieldStore(self.folder).create("Old", SQUARE)
        fields = FieldsManager(create_map_view("placeholder"))
        self.assertEqual(fields.count(), 1)

    def test_export(self):
        self.fields.add("A", SQUARE)
        self.fields.add("B", SQUARE)
        out = Path(self._tmp.name) / "out.geojson"
        self.assertEqual(self.fields.export(out), 2)
        names = [f["properties"]["name"] for f in json.loads(out.read_text("utf-8"))["features"]]
        self.assertEqual(names, ["A", "B"])


class FieldsWindowTest(_TempFields):
    def setUp(self):
        super().setUp()
        from fieldshift.ui import MainWindow
        self.view = create_map_view("placeholder")
        self.base = self.view.add_layer(LayerSpec.xyz("Satellite", "u", locked=True))
        self.window = MainWindow(self.view)
        self.panel = self.window.panel
        self.bar = self.window.fields_bar

    def labels(self):
        lst = self.panel.layer_list
        return [lst.item(i).text() for i in range(lst.count())]

    def select(self, layer_id):
        lst = self.panel.layer_list
        for i in range(lst.count()):
            if lst.item(i).data(QtCore.Qt.ItemDataRole.UserRole) == layer_id:
                lst.setCurrentRow(i)
                return lst.item(i)
        self.fail(f"layer {layer_id} not in the list")

    def draw(self, name):
        self.bar.draw_button.click()
        with mock.patch.object(self.bar, "_ask_name", return_value=name):
            self.view.simulate_polygon(SQUARE)
        fields = self.window.fields
        return next((i.id for i in self.view.layers()
                     if fields.is_field(i.id) and fields.field(i.id).name == name), None)

    def test_base_layers_are_hidden_but_stay_on_the_map(self):
        self.assertEqual(self.labels(), [])
        self.assertFalse(self.panel.empty_label.isHidden())
        self.assertEqual([i.id for i in self.view.layers()], [self.base])

    def test_draw_button_toggles_drawing(self):
        self.bar.draw_button.click()
        self.assertTrue(self.view.is_drawing())
        self.assertFalse(self.bar.hint_label.isHidden())
        self.assertEqual(self.bar.draw_button.text(), "Drawing… (Esc to cancel)")
        self.bar.draw_button.click()                       # second click cancels
        self.assertFalse(self.view.is_drawing())
        self.assertFalse(self.bar.draw_button.isChecked())
        self.assertTrue(self.bar.hint_label.isHidden())

    def test_save_drawn_field(self):
        self.assertFalse(self.bar.export_button.isEnabled())
        layer_id = self.draw("North plot")
        self.assertIsNotNone(layer_id)
        self.assertFalse(self.bar.draw_button.isChecked())
        self.assertEqual(self.labels(), ["North plot"])
        self.assertTrue(self.panel.empty_label.isHidden())
        self.assertTrue(self.bar.export_button.isEnabled())

    def test_cancelled_name_discards_the_drawing(self):
        self.assertIsNone(self.draw(None))
        self.assertEqual(FieldStore(self.folder).fields(), [])
        self.assertEqual(self.labels(), [])

    def test_click_on_field_zooms(self):
        layer_id = self.draw("A")
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.panel._on_item_clicked(self.select(layer_id))
        zoom.assert_called_once()

    def test_delete_field_asks_first(self):
        layer_id = self.draw("A")
        self.assertFalse(self.panel.delete_button.isEnabled())   # nothing selected
        self.select(layer_id)
        self.assertTrue(self.panel.delete_button.isEnabled())
        with mock.patch("fieldshift.ui.dialogs.confirm", return_value=False) as ask:
            self.panel._remove_selected()
        self.assertIn("A", ask.call_args.args[2])
        self.assertTrue(self.window.fields.is_field(layer_id))
        self.select(layer_id)
        with mock.patch("fieldshift.ui.dialogs.confirm", return_value=True):
            self.panel._remove_selected()
        self.assertFalse(self.window.fields.is_field(layer_id))
        self.assertEqual(self.labels(), [])
        self.assertEqual(list(self.folder.glob("*.geojson")), [])
        self.assertFalse(self.bar.export_button.isEnabled())

    def test_other_layers_are_listed_and_removed_without_asking(self):
        mine = self.view.add_layer(LayerSpec.vector("NDVI", "x.geojson"))
        self.assertEqual(self.labels(), ["NDVI  [vector]"])
        self.select(mine)
        self.panel._remove_selected()
        self.assertEqual([i.id for i in self.view.layers()], [self.base])


    def check(self, layer_id, checked=True):
        state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        self.select(layer_id).setCheckState(state)

    def test_real_click_on_checkbox_chooses_field_without_crash(self):
        # regression: rebuilding the list inside the checkbox signal deleted
        # the clicked item and PyQt aborted the app
        import importlib
        QtTest = importlib.import_module("qgis.PyQt.QtTest" if HAS_QGIS else "PyQt6.QtTest")
        from fieldshift.qt import QtWidgets
        layer_id = self.draw("A")
        self.window.resize(1200, 800)
        self.window.show()
        lst = self.panel.layer_list
        rect = lst.visualItemRect(lst.item(0))
        option = QtWidgets.QStyleOptionViewItem()
        option.rect = rect
        option.features = QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        box = lst.style().subElementRect(
            QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, lst)
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            QtTest.QTest.mouseClick(lst.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                    QtCore.Qt.KeyboardModifier.NoModifier, box.center())
            get_app().processEvents()
            self.assertEqual(self.window.fields.selected(), [layer_id])
            zoom.assert_not_called()                       # checkbox: choose only
            QtTest.QTest.mouseClick(lst.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                    QtCore.Qt.KeyboardModifier.NoModifier, rect.center())
            get_app().processEvents()
            zoom.assert_called_once()                      # name: zoom
        self.window.hide()

    def test_checked_fields_show_their_data(self):
        a = self.draw("A")
        b = self.draw("B")
        data = self.panel.data_box
        self.assertTrue(data.table.isHidden())
        self.check(a)
        self.check(b)
        self.assertEqual(data.table.rowCount(), 2)
        self.assertEqual(data.table.item(1, 0).text(), "B")
        area = self.window.fields.field(a).area_ha
        self.assertEqual(data.table.item(0, 1).text(), f"{area:.2f}")
        self.assertIn(f"{2 * area:.2f} ha", data.total_label.text())
        self.check(a, False)
        self.assertEqual(data.table.rowCount(), 1)

    def test_list_follows_selection_made_in_code(self):
        a = self.draw("A")
        self.window.fields.set_selected(a, True)
        self.assertEqual(self.select(a).checkState(), QtCore.Qt.CheckState.Checked)

    def test_export_checked_fields(self):
        self.draw("A")
        b = self.draw("B")
        self.assertEqual(self.bar.export_button.text(), "Export all fields…")
        self.check(b)
        self.assertEqual(self.bar.export_button.text(), "Export checked (1)…")
        out = str(Path(self._tmp.name) / "chosen")
        with mock.patch("fieldshift.qt.QtWidgets.QFileDialog.getSaveFileName",
                        return_value=(out, "")), \
                mock.patch("fieldshift.ui.dialogs.inform") as inform:
            self.bar._on_export_clicked()
        inform.assert_called_once()
        data = json.loads(Path(out + ".geojson").read_text("utf-8"))
        self.assertEqual([f["properties"]["name"] for f in data["features"]], ["B"])

    def test_delete_checked_fields(self):
        a = self.draw("A")
        b = self.draw("B")
        self.draw("C")
        self.check(a)
        self.check(b)
        self.assertTrue(self.panel.delete_button.isEnabled())
        with mock.patch("fieldshift.ui.dialogs.confirm", return_value=True) as ask:
            self.panel._remove_selected()
        self.assertIn("2", ask.call_args.args[2])
        self.assertEqual(self.labels(), ["C"])
        self.assertEqual(self.window.fields.selected(), [])


class FieldNameDialogTest(unittest.TestCase):
    def test_suggestion_and_validation(self):
        from fieldshift.ui.fields_bar import FieldNameDialog
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


class DialogsTest(unittest.TestCase):
    def test_confirm_returns_the_choice(self):
        from fieldshift.qt import QtWidgets
        from fieldshift.ui import dialogs

        def click_later(text):
            def run():
                for w in QtWidgets.QApplication.topLevelWidgets():
                    if isinstance(w, QtWidgets.QDialog) and w.isVisible():
                        next(b for b in w.findChildren(QtWidgets.QPushButton)
                             if b.text() == text).click()
            QtCore.QTimer.singleShot(0, run)

        click_later("Delete")
        self.assertTrue(dialogs.confirm(None, "t", "sure?", "Delete", danger=True))
        click_later("Cancel")
        self.assertFalse(dialogs.confirm(None, "t", "sure?", "Delete", danger=True))


if __name__ == "__main__":
    unittest.main()
