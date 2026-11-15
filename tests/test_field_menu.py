"""Tests for the right-click menu of a field on the map."""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.map import create_map_view  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]


def setUpModule():
    get_app()


class FieldMenuTest(unittest.TestCase):
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
        self.field = self.window.fields.add("North", SQUARE)

    def trigger(self, name):
        from fieldshift.qt import QtGui
        menu = self.window.field_menu.build(self.field)
        action = next(a for a in menu.actions() if a.objectName() == name)
        action.trigger()
        get_app().processEvents()                  # actions run after the menu closes
        return menu

    def test_menu_items(self):
        menu = self.window.field_menu.build(self.field)
        names = [a.objectName() for a in menu.actions() if a.objectName()]
        self.assertEqual(names, ["edit", "status", "analyze", "zoom", "check", "delete"])
        self.assertEqual(menu.actions()[0].text(), "North")      # title

    def test_actions(self):
        with mock.patch.object(self.window.panel, "edit_field") as edit:
            self.trigger("edit")
        edit.assert_called_once_with(self.field)
        with mock.patch.object(self.window, "analyze") as analyze:
            self.trigger("analyze")
        analyze.assert_called_once_with(self.field)
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.trigger("zoom")
        zoom.assert_called_once()
        self.trigger("check")
        self.assertEqual(self.window.fields.selected(), [self.field])
        menu = self.window.field_menu.build(self.field)
        self.assertEqual(next(a for a in menu.actions() if a.objectName() == "check").text(),
                         "Uncheck")
        with mock.patch("fieldshift.ui.dialogs.confirm", return_value=True):
            self.trigger("delete")
        self.assertEqual(self.window.fields.count(), 0)

    def test_right_click_opens_the_menu_only_on_fields(self):
        from fieldshift.qt import QtWidgets
        with mock.patch.object(QtWidgets.QMenu, "exec") as opened:
            self.view.simulate_right_click(self.field)
            self.window.fields_bar.draw_button.click()       # while drawing: nothing
            self.view.simulate_right_click(self.field)
        self.assertEqual(opened.call_count, 1)


class PanelWithoutExtraBoxesTest(unittest.TestCase):
    def test_no_position_or_tools_box(self):
        from fieldshift.qt import QtWidgets
        from fieldshift.ui import SidePanel
        i18n.set_language("en")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": tmp}):
            panel = SidePanel(create_map_view("placeholder"))
        titles = [b.title() for b in panel.findChildren(QtWidgets.QGroupBox)]
        self.assertEqual(sorted(titles), ["Field data", "My fields"])


if __name__ == "__main__":
    unittest.main()
