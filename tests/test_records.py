"""Field records (measurements with date and time) and how Status / Trends
use them; panels say why data is missing instead of showing made-up numbers."""

import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from qt_app import get_app

from fieldshift import i18n  # noqa: E402
from fieldshift.fields.records import EDITED, Record, parse_records  # noqa: E402
from fieldshift.map import create_map_view  # noqa: E402
from fieldshift.status.build import today_tiles  # noqa: E402
from fieldshift.status.example import example_forecast  # noqa: E402
from fieldshift.status.progress import crop_progress  # noqa: E402
from fieldshift.trends.build import measured_series  # noqa: E402

SQUARE = [(-70.70, -33.60), (-70.69, -33.60), (-70.69, -33.59), (-70.70, -33.59)]


def setUpModule():
    get_app()


class RecordsTest(unittest.TestCase):

    def setUp(self):
        from fieldshift.fields.manager import FieldsManager
        i18n.set_language("en")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": self._tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.view = create_map_view("placeholder")
        self.fields = FieldsManager(self.view)
        self.layer = self.fields.add("A", SQUARE)

    def test_saved_with_date_and_time_and_update_the_datum(self):
        self.fields.add_record(self.layer, Record("2026-11-10T09:30", "ph", 6.4, "lab"))
        self.fields.add_record(self.layer, Record("2026-11-12T16:05", "ph", 6.9))
        field = self.fields.field(self.layer)
        self.assertEqual([r.time for r in field.records],
                         ["2026-11-10T09:30", "2026-11-12T16:05"])
        self.assertEqual(field.data["ph"], {**field.data["ph"], "value": 6.9, "source": "user"})
        # the file keeps them (read back from disk)
        stored = self.fields.store.get("A")
        self.assertEqual(stored.records, field.records)
        self.assertEqual(parse_records([{"time": "bad", "kind": "ph"}]), ())

    def test_edit_field_values_become_records(self):
        field = self.fields.field(self.layer)
        data = dict(field.data, nitrogen={"value": 1.5, "source": "user"})
        new_id = self.fields.update(self.layer, "A", data=data)
        records = self.fields.records(new_id)
        self.assertEqual([(r.kind, r.value, r.origin) for r in records],
                         [("nitrogen", 1.5, EDITED)])

    def test_measured_today_replaces_the_forecast_tile(self):
        field = self.fields.field(self.layer)
        forecast = example_forecast(field, date(2026, 11, 15))
        records = (Record("2026-11-15T10:20", "soil_moisture", 27.0),
                   Record("2026-11-14T10:20", "soil_temp", 9.0))      # not today: ignored
        tiles = {t.key: t for t in today_tiles(forecast, records)}
        self.assertEqual((tiles["soil_moisture"].value, tiles["soil_moisture"].measured),
                         (27.0, "10:20"))
        self.assertEqual(tiles["soil_temp"].measured, "")

    def test_progress_and_trends_measured(self):
        records = (Record("2026-10-01T08:00", "sowing"),
                   Record("2026-11-01T08:00", "plant_height", 20.0),
                   Record("2026-11-10T08:00", "plant_height", 26.0))
        progress = crop_progress(records, date(2026, 11, 10))
        self.assertEqual((progress.days_since_sowing, progress.height), (40, 26.0))
        self.assertAlmostEqual(progress.height_change_pct, 30.0)
        series = measured_series(records, ("2026-10", "2026-11"))
        self.assertEqual(series, {"plant_height": [None, 23.0]})

    def test_records_dialog_adds_and_deletes(self):
        from fieldshift.ui.records_dialog import RecordsDialog
        dialog = RecordsDialog(self.fields, self.layer)
        dialog.kind_box.setCurrentIndex(dialog.kind_box.findData("plant_height"))
        dialog.value_box.setValue(31)
        dialog.add_from_form()
        self.assertEqual(dialog.table.rowCount(), 1)
        with mock.patch("fieldshift.ui.dialogs.confirm", return_value=True):
            dialog.table.selectRow(0)
            dialog.delete_selected()
        self.assertEqual(self.fields.records(self.layer), ())


class NoMadeUpDataTest(unittest.TestCase):

    def test_offline_panel_says_why_and_retries(self):
        from fieldshift.ui.main_window import MainWindow
        i18n.set_language("en")
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(
                os.environ, {"FIELDSHIFT_FIELDS_DIR": folder, "FIELDSHIFT_EXAMPLE_DATA": "0"}):
            window = MainWindow(create_map_view("placeholder"))
            layer = window.fields.add("A", SQUARE)
            self.assertTrue(window.open_trends(layer))
            panel = window.trends_panel
            self.assertIsNone(panel.report)
            self.assertIn("working offline", panel.error_box.label.text())
            self.assertEqual(panel.error_box.retry_button.text(), "Try again")
            window.close()
