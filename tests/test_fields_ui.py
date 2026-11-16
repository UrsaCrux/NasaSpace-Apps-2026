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

    def test_update_changes_layer_name_colour_and_file(self):
        specs = []
        original = self.view.add_layer
        self.view.add_layer = lambda spec: (specs.append(spec), original(spec))[1]
        old_id = self.fields.add("A", SQUARE)
        self.fields.set_selected(old_id, True)
        changes = []
        self.fields.fields_changed.connect(lambda: changes.append(1))
        new_id = self.fields.update(old_id, "B", "#00ff00", {"ph": {"value": 4.0, "source": "user"}})
        self.assertFalse(self.fields.is_field(old_id))
        self.assertEqual([i.name for i in self.view.layers()], ["B"])         # old layer gone
        self.assertEqual(specs[-1].options["fill_color"], "#5500ff00")
        self.assertEqual(self.fields.selected(), [new_id])                    # still checked
        self.assertEqual(self.fields.field(new_id).data["ph"]["value"], 4.0)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["B.geojson"])
        self.assertEqual(changes, [1])

    def test_update_keeps_an_unchecked_field_unchecked(self):
        old_id = self.fields.add("A", SQUARE)
        new_id = self.fields.update(old_id, "A", "#00ff00")
        self.assertEqual(self.fields.selected(), [])
        self.assertTrue(self.fields.is_field(new_id))

    def test_failed_update_changes_nothing(self):
        layer_id = self.fields.add("A", SQUARE, color="#112233")
        self.fields.add("B", SQUARE)
        with self.assertRaises(ValueError):
            self.fields.update(layer_id, "b")                                 # taken
        with mock.patch.object(self.view, "add_layer", side_effect=ValueError("bad")):
            with self.assertRaises(ValueError):
                self.fields.update(layer_id, "C", "#ffffff")                  # layer fails
        self.assertEqual(sorted(f.name for f in FieldStore(self.folder).fields()), ["A", "B"])
        self.assertEqual(FieldStore(self.folder).get("A").color, "#112233")   # undone
        self.assertTrue(self.fields.is_field(layer_id))

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

    def test_checked_fields_are_outlined_on_the_map(self):
        a = self.fields.add("A", SQUARE)
        b = self.fields.add("B", [(-71.0, -33.7), (-70.99, -33.7), (-70.99, -33.71)])
        self.assertEqual(self.view.marked(), [])
        self.fields.set_selected(b, True)
        self.assertEqual(self.view.marked(), [list(self.fields.field(b).vertices)])
        self.fields.set_selected(a, True)
        self.assertEqual(len(self.view.marked()), 2)
        self.fields.remove(b)                       # deleted: no longer outlined
        self.assertEqual(self.view.marked(), [list(self.fields.field(a).vertices)])
        self.fields.set_selected(a, False)
        self.assertEqual(self.view.marked(), [])

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


class _WindowCase(_TempFields):
    """A window around a placeholder map with a locked base layer, and helpers."""

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

    def draw(self, name, color=None, data=None):
        self.bar.draw_button.click()
        details = (name, color, data) if name else None
        with mock.patch.object(self.bar, "_ask_details", return_value=details):
            self.view.simulate_polygon(SQUARE)
        fields = self.window.fields
        return next((i.id for i in self.view.layers()
                     if fields.is_field(i.id) and fields.field(i.id).name == name), None)


class FieldsWindowTest(_WindowCase):
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

    def test_double_click_on_a_field_in_the_map_toggles_its_checkbox(self):
        a = self.draw("A")
        b = self.draw("B")
        self.view.simulate_double_click(b, -70.69, -33.40)
        self.assertEqual(self.window.fields.selected(), [b])
        self.assertEqual(self.select(b).checkState(), QtCore.Qt.CheckState.Checked)
        self.assertEqual(self.panel.layer_list.currentItem().data(QtCore.Qt.ItemDataRole.UserRole), b)
        self.assertEqual(self.panel.data_box.field_count(), 1)
        self.view.simulate_double_click(a, -70.69, -33.40)
        self.assertEqual(self.window.fields.selected(), [a, b])
        self.view.simulate_double_click(b, -70.69, -33.40)         # ticked: unticks
        self.assertEqual(self.window.fields.selected(), [a])
        self.assertEqual(self.panel.layer_list.currentItem().data(QtCore.Qt.ItemDataRole.UserRole), b)

    def test_double_click_while_drawing_or_on_other_layers_does_nothing(self):
        a = self.draw("A")
        other = self.view.add_layer(LayerSpec.vector("NDVI", "x.geojson"))
        self.view.layer_double_clicked.emit(other, 0, 0)           # not a field
        self.assertEqual(self.window.fields.selected(), [])
        self.bar.draw_button.click()                               # drawing
        self.panel._on_map_double_click(a, 0, 0)
        self.assertEqual(self.window.fields.selected(), [])

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
        self.assertTrue(data.tree.isHidden())
        self.check(a)
        self.check(b)
        self.assertEqual(data.field_count(), 2)
        node = data.tree.topLevelItem(1)
        self.assertEqual(node.text(0), "B")
        area = self.window.fields.field(a).area_ha
        self.assertEqual(data.tree.topLevelItem(0).text(1), f"{area:.2f} ha")
        self.assertIn(f"{2 * area:.2f} ha", data.total_label.text())
        # below each field: creation date, crop, then every datum of DATA_FIELDS
        from fieldshift.fields.schema import DATA_FIELDS
        self.assertEqual(node.childCount(), 2 + len(DATA_FIELDS))
        self.assertEqual((node.child(1).text(0), node.child(1).text(1)), ("Crop", "no crop chosen"))
        self.assertEqual(node.child(2).text(0), "Soil texture")
        self.assertEqual((node.child(2).text(1), node.child(2).toolTip(1)), ("—", "not available"))
        self.check(a, False)
        self.assertEqual(data.field_count(), 1)

    def test_field_color_and_data_reach_the_map_and_the_data_box(self):
        specs = []
        original = self.view.add_layer
        self.view.add_layer = lambda spec: (specs.append(spec), original(spec))[1]
        data = {"soil_texture": {"value": "sand", "source": "user", "prefilled": "loam"},
                "ph": {"value": 6.4, "source": "prefilled"},
                "crop": {"value": "peach.v1", "source": "user"}}
        layer_id = self.draw("Red", color="#ff0000", data=data)
        self.assertEqual(specs[-1].options["fill_color"], "#55ff0000")
        self.assertEqual(specs[-1].options["stroke_color"], "#990000")
        self.window.fields.set_selected(layer_id, True)
        node = self.panel.data_box.tree.topLevelItem(0)
        self.assertEqual(node.child(1).text(1), "Peach – variety 1")
        rows = {node.child(i).text(0): node.child(i) for i in range(node.childCount())}
        soil, ph = rows["Soil texture"], rows["pH"]
        self.assertEqual((soil.text(1), soil.toolTip(1)), ("Sand", "edited"))
        self.assertEqual((ph.text(1), ph.toolTip(1)), ("6.4", "preloaded"))
        gray = self.draw("Plain")
        self.assertEqual(self.window.fields.field(gray).color, "#9e9e9e")
        self.assertEqual(specs[-1].options["fill_color"], "#559e9e9e")

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


class EditFieldTest(_WindowCase):
    """The Edit button of a field row."""

    def edit_button_pos(self, layer_id):
        from fieldshift.ui.field_list import edit_button_rect
        self.window.resize(1200, 800)
        self.window.show()
        lst = self.panel.layer_list
        row = lst.visualItemRect(self.select(layer_id))
        return lst, edit_button_rect(row, lst.fontMetrics()).center()

    def click(self, lst, pos):
        import importlib
        QtTest = importlib.import_module("qgis.PyQt.QtTest" if HAS_QGIS else "PyQt6.QtTest")
        QtTest.QTest.mouseClick(lst.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier, pos)
        get_app().processEvents()          # the dialog opens after the click is handled

    def fill_dialog(self, name=None, color=None, ph=None):
        from fieldshift.ui.field_dialog import FieldDialog

        def run(dialog):
            self.seen = dialog
            if name is not None:
                dialog.name_edit.setText(name)
            if color is not None:
                dialog._color = color
            if ph is not None:
                dialog.set_value("ph", ph)
            return FieldDialog.DialogCode.Accepted
        return mock.patch.object(FieldDialog, "exec", new=run)

    def test_edit_button_opens_the_dialog_with_the_current_data(self):
        layer_id = self.draw("A", color="#112233",
                             data={"ph": {"value": 5.5, "source": "user"},
                                   "crop": {"value": "apple.v1", "source": "user"}})
        lst, pos = self.edit_button_pos(layer_id)
        with self.fill_dialog():
            self.click(lst, pos)
        dialog = self.seen
        self.assertEqual((dialog.name(), dialog.color()), ("A", "#112233"))
        self.assertEqual(dialog.windowTitle(), "Edit field")
        self.assertEqual(dialog.data()["ph"], {"value": 5.5, "source": "user"})
        self.assertEqual(dialog.crop(), "apple.v1")
        self.assertTrue(dialog.is_modified("ph"))
        self.assertFalse(dialog.is_modified("soil_texture"))
        self.assertTrue(dialog.save_button.isEnabled())             # own name is allowed
        self.assertIs(dialog.parentWidget(), self.window)

    def test_saving_updates_map_list_data_box_and_file_and_keeps_the_check(self):
        layer_id = self.draw("A")
        self.window.fields.set_selected(layer_id, True)
        lst, pos = self.edit_button_pos(layer_id)
        with self.fill_dialog(name="Renamed", color="#ff0000", ph=4.2):
            self.click(lst, pos)
        fields = self.window.fields
        self.assertEqual(self.labels(), ["Renamed"])
        self.assertEqual([i.name for i in self.view.layers() if i.name == "Renamed"], ["Renamed"])
        new_id = fields.selected()[0]                                  # still checked
        self.assertEqual(fields.field(new_id).color, "#ff0000")
        self.assertEqual(self.select(new_id).checkState(), QtCore.Qt.CheckState.Checked)
        node = self.panel.data_box.tree.topLevelItem(0)
        self.assertEqual(node.text(0), "Renamed")
        ph = next(node.child(i) for i in range(node.childCount()) if node.child(i).text(0) == "pH")
        self.assertEqual((ph.text(1), ph.toolTip(1)), ("4.2", "edited"))
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), ["Renamed.geojson"])

    def test_cancel_changes_nothing(self):
        from fieldshift.ui.field_dialog import FieldDialog
        layer_id = self.draw("A")
        lst, pos = self.edit_button_pos(layer_id)
        with mock.patch.object(FieldDialog, "exec", return_value=FieldDialog.DialogCode.Rejected):
            self.click(lst, pos)
        self.assertTrue(self.window.fields.is_field(layer_id))
        self.assertEqual(self.labels(), ["A"])

    def test_clicking_the_button_neither_zooms_nor_checks(self):
        layer_id = self.draw("A")
        lst, pos = self.edit_button_pos(layer_id)
        with self.fill_dialog(), mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.click(lst, pos)
        zoom.assert_not_called()
        self.assertEqual(self.window.fields.selected(), [])

    def test_rows_are_tall_enough_for_the_edit_button(self):
        from fieldshift.ui.field_list import ROW_HEIGHT, edit_button_rect
        layer_id = self.draw("A")
        self.window.resize(1200, 800)
        self.window.show()
        lst = self.panel.layer_list
        row = lst.visualItemRect(self.select(layer_id))
        button = edit_button_rect(row, lst.fontMetrics())
        self.assertGreaterEqual(row.height(), ROW_HEIGHT)
        self.assertGreaterEqual(button.height(), lst.fontMetrics().height() + 4)   # text fits
        self.assertTrue(row.contains(button))
        self.window.hide()

    def test_other_layers_have_no_edit_button(self):
        from fieldshift.ui.field_list import EDITABLE_ROLE, edit_button_rect
        mine = self.view.add_layer(LayerSpec.vector("NDVI", "x.geojson"))
        field = self.draw("A")
        self.assertFalse(self.select(mine).data(EDITABLE_ROLE))
        self.assertTrue(self.select(field).data(EDITABLE_ROLE))
        lst = self.panel.layer_list
        self.window.resize(1200, 800)
        self.window.show()
        row = lst.visualItemRect(self.select(mine))
        self.assertIsNone(lst.edit_button_at(edit_button_rect(row, lst.fontMetrics()).center()))

    def test_dialog_opens_centred_on_the_window(self):
        from fieldshift.ui.field_dialog import FieldDialog
        layer_id = self.draw("A")
        self.window.move(100, 80)
        self.window.resize(1200, 800)
        self.window.show()
        dialog = FieldDialog(self.window.fields.store, field=self.window.fields.field(layer_id),
                             parent=self.window)
        dialog.show()
        get_app().processEvents()
        center, window_center = dialog.frameGeometry().center(), self.window.frameGeometry().center()
        self.assertLess(abs(center.x() - window_center.x()), 3)
        self.assertLess(abs(center.y() - window_center.y()), 3)
        dialog.close()
        self.window.hide()


# values a data source would give, per zone_data group
FAKE_VALUES = {"copernicus_dem": {"elevation": 512.0, "slope": 3.5},
               "wapor": {"npp": 4.2, "actual_et": 3.1},
               "soilgrids": {"soil_texture": "loam", "soil_group": "luvisols",
                             "clay": 21.0, "sand": 42.0, "silt": 37.0, "ph": 6.4,
                             "organic_carbon": 18.5, "nitrogen": 1.6, "cec": 17.0,
                             "available_water": 14.2},
               "modis_ndvi": {"ndvi": 0.71}}


# (SourceGroup group, Area area)
# instant fetch for FieldDialog(fetch=...)
def fake_fetch(group, area):
    return dict(FAKE_VALUES[group.name])


# (callable condition, float timeout = 5)
# processes Qt events until condition() is true; fails the test on timeout
def wait_until(condition, timeout=5.0):
    import time
    end = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > end:
            raise AssertionError("condition not met in time")
        get_app().processEvents()
        time.sleep(0.01)


class FieldDialogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = FieldStore(self._tmp.name)
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "en")

    def dialog(self, **kw):
        from fieldshift.ui.field_dialog import FieldDialog
        return FieldDialog(self.store, **kw)

    def test_name_is_suggested_required_and_unique(self):
        i18n.set_language("es")
        self.store.create("Terreno 1", SQUARE)
        dialog = self.dialog(vertices=SQUARE)
        self.assertEqual(dialog.name(), "Terreno 2")
        self.assertTrue(dialog.save_button.isEnabled())          # the crop is optional
        dialog.crop_search.choose("peach.v1")
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.name_edit.setText("terreno 1")
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn("Ya existe", dialog.error_label.text())
        dialog.name_edit.setText("   ")
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.name_edit.setText("Terreno 9")
        self.assertTrue(dialog.error_label.isHidden())          # no empty gap when valid

    def test_color_is_grey_unless_chosen(self):
        from fieldshift.qt import QtGui, QtWidgets
        dialog = self.dialog(vertices=SQUARE)
        self.assertEqual(dialog.color(), "#9e9e9e")
        with mock.patch.object(QtWidgets.QColorDialog, "getColor",
                               return_value=QtGui.QColor("#2E7D32")):
            dialog.color_button.click()
        self.assertEqual(dialog.color(), "#2e7d32")
        with mock.patch.object(QtWidgets.QColorDialog, "getColor",
                               return_value=QtGui.QColor()):           # cancelled
            dialog.color_button.click()
        self.assertEqual(dialog.color(), "#2e7d32")

    def test_data_starts_loaded_and_can_be_edited_and_restored(self):
        from fieldshift.fields.schema import CROP_KEY, DATA_FIELDS
        dialog = self.dialog(vertices=SQUARE, fetch=fake_fetch)
        wait_until(lambda: not dialog.is_loading())
        data = dialog.data()
        self.assertEqual(set(data), {s.key for s in DATA_FIELDS} | {CROP_KEY})
        self.assertEqual(data["ph"], {"value": 6.4, "source": "prefilled", "prefilled": 6.4})
        for spec in DATA_FIELDS:
            self.assertFalse(dialog.is_modified(spec.key))
        dialog.set_value("ph", 4.5)
        dialog.set_value("soil_texture", "sand")
        dialog.set_value("irrigated", True)
        data = dialog.data()
        self.assertEqual((data["ph"]["value"], data["ph"]["source"]), (4.5, "user"))
        self.assertEqual(data["soil_texture"],
                         {"value": "sand", "source": "user", "prefilled": "loam"})
        self.assertEqual(data["irrigated"], {"value": True, "source": "user"})
        self.assertEqual(data["slope"]["value"], 3.5)                       # untouched
        dialog.reset_value("ph")
        self.assertEqual(dialog.data()["ph"], {"value": 6.4, "source": "prefilled",
                                               "prefilled": 6.4})
        self.assertFalse(dialog.is_modified("ph"))

    def test_typing_in_the_editor_marks_the_datum_as_edited(self):
        dialog = self.dialog(vertices=SQUARE, fetch=fake_fetch)
        wait_until(lambda: not dialog.is_loading())
        edit = dialog._rows["ph"]["editor"]
        edit.setText("7.7")
        edit.textEdited.emit("7.7")                     # what typing emits
        self.assertTrue(dialog.is_modified("ph"))
        self.assertEqual(dialog.data()["ph"]["value"], 7.7)
        self.assertFalse(dialog._rows["ph"]["reset"].isHidden())        # restore button shown
        self.assertTrue(dialog._rows["soil_texture"]["reset"].isHidden())  # untouched: hidden
        combo = dialog._rows["irrigated"]["editor"]
        combo.setCurrentIndex(1)
        combo.activated.emit(1)                         # what a user click emits
        self.assertTrue(dialog.is_modified("irrigated"))


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
