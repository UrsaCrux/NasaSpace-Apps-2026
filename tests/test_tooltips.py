"""Tooltips of the field dialog come from fieldshift/i18n/tooltips/tooltips.json."""

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.fields import FieldStore  # noqa: E402
from fieldshift.fields.schema import DATA_FIELDS, GROUPS  # noqa: E402
from qt_app import get_app  # noqa: E402
from test_fields_ui import SQUARE  # noqa: E402


def setUpModule():
    get_app()


class TooltipFileTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_every_key_has_english_and_spanish(self):
        data = json.loads(i18n.TOOLTIPS_PATH.read_text("utf-8"))
        for key, texts in data.items():
            if key.startswith("_"):
                continue
            self.assertTrue(texts.get("en") and texts.get("es"), key)

    def test_language_and_fallbacks(self):
        i18n.set_language("es")
        self.assertIn("Texto provisorio", i18n.tip("field_dialog.name"))
        i18n.set_language("en")
        self.assertIn("Placeholder", i18n.tip("field_dialog.name"))
        self.assertEqual(i18n.tip("no.such.key"), "")

    def test_tooltips_are_not_a_language(self):
        self.assertEqual(i18n.available_languages(), ["en", "es"])


class FieldDialogTooltipsTest(unittest.TestCase):
    def test_every_title_and_button_has_its_tooltip(self):
        from fieldshift.ui.field_dialog import FieldDialog
        i18n.set_language("en")
        dialog = FieldDialog(FieldStore(tempfile.mkdtemp()), vertices=SQUARE)
        self.addCleanup(dialog.done, 0)
        expected = {"field_dialog.name", "field_dialog.crop", "field_dialog.color",
                    "field_dialog.color_button", "field_dialog.data_box",
                    "field_dialog.save", "field_dialog.cancel"}
        expected |= {f"field_dialog.group.{g}" for g in GROUPS}
        expected |= {f"field_dialog.data.{s.key}" for s in DATA_FIELDS}
        self.assertEqual(set(dialog.tooltip_widgets), expected)
        for key, widget in dialog.tooltip_widgets.items():
            self.assertEqual(widget.toolTip(), i18n.tip(key), key)
            self.assertTrue(widget.toolTip(), key)
        for row in dialog._rows.values():                       # every restore button
            self.assertEqual(row["reset"].toolTip(), i18n.tip("field_dialog.reset_button"))


if __name__ == "__main__":
    unittest.main()
