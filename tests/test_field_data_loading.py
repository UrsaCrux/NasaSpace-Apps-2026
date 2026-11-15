"""Tests for the zone data loading of the field dialog, the crop search and
fieldshift.fields.zone_data (no network: data sources are faked)."""

import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import crops, i18n  # noqa: E402
from fieldshift.fields import FieldStore, zone_data  # noqa: E402
from qt_app import get_app  # noqa: E402
from test_fields_ui import FAKE_VALUES, SQUARE, fake_fetch, wait_until  # noqa: E402


def setUpModule():
    get_app()


class _DialogCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = FieldStore(self._tmp.name)
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "en")

    def dialog(self, **kw):
        from fieldshift.ui.field_dialog import FieldDialog
        dialog = FieldDialog(self.store, **kw)
        self.addCleanup(dialog.done, 0)
        return dialog


class LoadingTest(_DialogCase):
    def test_rows_animate_and_save_waits_until_every_source_answers(self):
        release = {name: threading.Event() for name in FAKE_VALUES}

        def slow_fetch(group, area):
            release[group.name].wait(5)
            return dict(FAKE_VALUES[group.name])

        dialog = self.dialog(vertices=SQUARE, fetch=slow_fetch)
        dialog.crop_search.choose("peach.v1")
        self.assertTrue(dialog.is_loading())
        self.assertEqual(dialog.row_state("ph"), "loading")
        self.assertEqual(dialog.row_state("irrigated"), "farmer")       # not fetched
        self.assertFalse(dialog.save_button.isEnabled())
        ph = dialog._rows["ph"]["editor"]
        self.assertFalse(ph.isEnabled())
        first = ph.placeholderText()
        wait_until(lambda: ph.placeholderText() != first)                # animated
        self.assertIn("loading", ph.placeholderText())
        self.assertIn("0/4", dialog.load_label.text())

        dialog.accept()                                                  # Enter: refused
        self.assertEqual(dialog.result(), 0)

        release["copernicus_dem"].set()                                  # one source answers
        wait_until(lambda: dialog.row_state("elevation") == "prefilled")
        self.assertEqual(dialog.data()["elevation"]["value"], 512.0)
        self.assertEqual(dialog.row_state("ph"), "loading")
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertIn("1/4", dialog.load_label.text())

        for event in release.values():
            event.set()
        wait_until(lambda: not dialog.is_loading())
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(dialog.row_state("ph"), "prefilled")
        self.assertEqual(ph.text(), "6.4")
        self.assertEqual(dialog.load_label.text(), "Zone data loaded.")

    def test_failed_source_leaves_orange_not_available_rows(self):
        def flaky(group, area):
            if group.name == "soilgrids":
                raise TimeoutError("SoilGrids did not answer")
            return dict(FAKE_VALUES[group.name])

        dialog = self.dialog(vertices=SQUARE, fetch=flaky)
        dialog.crop_search.choose("wheat.v2")
        wait_until(lambda: not dialog.is_loading())
        self.assertTrue(dialog.save_button.isEnabled())                 # never blocked forever
        for key in FAKE_VALUES["soilgrids"]:
            self.assertEqual(dialog.row_state(key), "missing")
        ph = dialog._rows["ph"]
        self.assertEqual(ph["editor"].placeholderText(), "not available")
        self.assertIn("#fff4e5", ph["editor"].styleSheet())             # other colour
        self.assertIn("TimeoutError", ph["status"].toolTip())
        self.assertIn("SoilGrids", dialog.load_label.text())
        self.assertEqual(dialog.data()["ph"], {"value": None, "source": "missing"})
        self.assertEqual(dialog.data()["slope"]["source"], "prefilled")
        # the user can still type a missing value
        ph["editor"].setText("6.9")
        ph["editor"].textEdited.emit("6.9")
        self.assertEqual(dialog.data()["ph"], {"value": 6.9, "source": "user"})

    def test_a_source_with_no_value_for_a_key_marks_only_that_key(self):
        def partial(group, area):
            values = dict(FAKE_VALUES[group.name])
            if group.name == "modis_ndvi":
                values["ndvi"] = None                                   # cloudy, no data
            return values
        dialog = self.dialog(vertices=SQUARE, fetch=partial)
        wait_until(lambda: not dialog.is_loading())
        self.assertEqual(dialog.row_state("ndvi"), "missing")
        self.assertEqual(dialog.row_state("npp"), "prefilled")

    def test_deadline_gives_up_on_slow_sources(self):
        never = threading.Event()
        self.addCleanup(never.set)

        def hang(group, area):
            if group.name == "modis_ndvi":
                never.wait(10)
            return dict(FAKE_VALUES[group.name])

        with mock.patch.object(zone_data, "DEADLINE_S", 0.3):
            dialog = self.dialog(vertices=SQUARE, fetch=hang)
            wait_until(lambda: not dialog.is_loading())
        self.assertEqual(dialog.row_state("ndvi"), "missing")
        self.assertEqual(dialog.row_state("ph"), "prefilled")
        self.assertIn("MODIS NDVI", dialog.load_label.text())

    def test_each_source_has_its_own_timeout(self):
        never = threading.Event()
        self.addCleanup(never.set)

        def hang(group, area):
            if group.name == "modis_ndvi":
                never.wait(10)
            return dict(FAKE_VALUES[group.name])

        groups = tuple(zone_data.SourceGroup(g.name, g.keys, g.make_provider, g.extract,
                                             0.3 if g.name == "modis_ndvi" else 30, g.title)
                       for g in zone_data.SOURCE_GROUPS)
        with mock.patch.object(zone_data, "SOURCE_GROUPS", groups):
            dialog = self.dialog(vertices=SQUARE, fetch=hang)
            wait_until(lambda: not dialog.is_loading())
        self.assertEqual(dialog.row_state("ndvi"), "missing")
        self.assertEqual(dialog.row_state("slope"), "prefilled")
        self.assertTrue(all(g.timeout_s <= zone_data.DEADLINE_S
                            for g in zone_data.SOURCE_GROUPS))

    def test_editing_keeps_user_values_and_only_loads_empty_rows(self):
        field = self.store.create("A", SQUARE, data={
            "ph": {"value": 5.5, "source": "user"},
            "elevation": {"value": 400.0, "source": "prefilled"},
            "crop": {"value": "pear.v3", "source": "user"}})
        asked = []

        def record(group, area):
            asked.append(group.name)
            return dict(FAKE_VALUES[group.name])

        dialog = self.dialog(field=field, fetch=record)
        wait_until(lambda: not dialog.is_loading())
        self.assertEqual(dialog.data()["ph"]["value"], 5.5)                 # kept
        self.assertEqual(dialog.data()["ph"]["source"], "user")
        self.assertEqual(dialog.data()["ph"]["prefilled"], 6.4)             # now restorable
        self.assertFalse(dialog._rows["ph"]["reset"].isHidden())
        self.assertEqual(dialog.data()["elevation"]["value"], 400.0)        # kept
        self.assertEqual(dialog.data()["slope"]["value"], 3.5)              # loaded
        self.assertEqual(dialog.crop(), "pear.v3")
        self.assertTrue(dialog.save_button.isEnabled())

    def test_an_existing_field_can_be_saved_while_loading(self):
        field = self.store.create("A", SQUARE, data={
            "ph": {"value": 5.5, "source": "user"},
            "crop": {"value": "pear.v3", "source": "user"}})
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(group, area):
            if group.name != "copernicus_dem":
                release.wait(5)
            return dict(FAKE_VALUES[group.name])

        dialog = self.dialog(field=field, fetch=slow)
        wait_until(lambda: dialog.row_state("slope") == "prefilled")
        self.assertTrue(dialog.is_loading())
        self.assertTrue(dialog.save_button.isEnabled())            # not blocked when editing
        self.assertIn("save now", dialog.load_label.text())
        dialog.accept()
        self.assertEqual(dialog.result(), 1)                       # saved
        self.assertFalse(dialog.is_loading())                      # loading stopped
        data = dialog.data()
        self.assertEqual(data["ph"], {"value": 5.5, "source": "user"})        # kept
        self.assertEqual(data["slope"]["value"], 3.5)                          # had arrived
        self.assertEqual(data["ndvi"], {"value": None, "source": "missing"})   # stopped
        release.set()
        get_app().processEvents()
        self.assertEqual(dialog.data()["ndvi"]["value"], None)    # late answer ignored

    def test_a_new_field_still_waits(self):
        release = threading.Event()
        self.addCleanup(release.set)
        dialog = self.dialog(vertices=SQUARE,
                             fetch=lambda g, a: (release.wait(5), dict(FAKE_VALUES[g.name]))[1])
        dialog.crop_search.choose("peach.v1")
        self.assertFalse(dialog.editing)
        self.assertFalse(dialog.save_button.isEnabled())

    def test_nothing_is_loaded_when_every_row_has_a_value(self):
        data = {k: {"value": v, "source": "prefilled"}
                for values in FAKE_VALUES.values() for k, v in values.items()}
        field = self.store.create("Full", SQUARE, data=data)
        fetch = mock.Mock()
        dialog = self.dialog(field=field, fetch=fetch)
        self.assertFalse(dialog.is_loading())
        fetch.assert_not_called()

    def test_offline_marks_empty_rows_missing_at_once(self):
        with mock.patch.dict(os.environ, {"FIELDSHIFT_OFFLINE": "1"}):
            dialog = self.dialog(vertices=SQUARE)
        self.assertFalse(dialog.is_loading())
        self.assertEqual(dialog.row_state("ph"), "missing")


class ReloadTest(_DialogCase):
    def test_reload_downloads_one_datum_again(self):
        calls = []
        answers = {"ph": 6.4}

        def fetch(group, area):
            calls.append(group.name)
            values = dict(FAKE_VALUES[group.name])
            values.update({k: v for k, v in answers.items() if k in values})
            return values
        dialog = self.dialog(vertices=SQUARE, fetch=fetch)
        wait_until(lambda: not dialog.is_loading())
        dialog.set_value("ph", 5.0)                              # the user's value
        dialog.set_value("cec", 9.0)
        answers["ph"] = 7.1                                       # the source changed
        calls.clear()
        dialog._rows["ph"]["reload"].click()
        self.assertTrue(dialog.is_reloading("ph"))
        wait_until(lambda: not dialog.is_reloading("ph"))
        self.assertEqual(calls, ["soilgrids"])
        self.assertEqual(dialog.data()["ph"], {"value": 7.1, "source": "prefilled",
                                               "prefilled": 7.1})
        self.assertEqual(dialog.data()["cec"]["value"], 9.0)      # other rows untouched
        self.assertTrue(dialog._rows["irrigated"]["reload"].isHidden())   # farmer data
        self.assertFalse(dialog._rows["ph"]["reload"].isHidden())

    def test_failed_reload_keeps_the_value(self):
        state = {"fail": False}

        def fetch(group, area):
            if state["fail"]:
                raise ConnectionError("offline")
            return dict(FAKE_VALUES[group.name])
        dialog = self.dialog(vertices=SQUARE, fetch=fetch)
        wait_until(lambda: not dialog.is_loading())
        state["fail"] = True
        dialog.reload_value("slope")
        wait_until(lambda: not dialog.is_reloading("slope"))
        self.assertEqual(dialog.data()["slope"]["value"], 3.5)
        self.assertEqual(dialog.row_state("slope"), "prefilled")
        self.assertIn("ConnectionError", dialog._rows["slope"]["status"].toolTip())

    def test_reload_skips_the_cache(self):
        dialog = self.dialog(vertices=SQUARE, fetch=fake_fetch)
        wait_until(lambda: not dialog.is_loading())
        dialog._fetch = None                                      # the real path
        with mock.patch.object(zone_data, "fetch_group",
                               return_value=dict(FAKE_VALUES["modis_ndvi"], ndvi=0.5)) as fetch, \
                mock.patch.dict(os.environ, {"FIELDSHIFT_OFFLINE": "0"}):
            dialog.reload_value("ndvi")
            wait_until(lambda: not dialog.is_reloading("ndvi"))
        self.assertTrue(fetch.call_args.kwargs.get("refresh"))
        self.assertEqual(dialog.data()["ndvi"]["value"], 0.5)


class DialogSizeTest(_DialogCase):
    def test_scrolls_and_opens_as_tall_as_the_window_minus_a_margin(self):
        from fieldshift.map import create_map_view
        from fieldshift.ui import MainWindow
        from fieldshift.ui.field_dialog import WINDOW_MARGIN_PX
        with mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": self._tmp.name}):
            window = MainWindow(create_map_view("placeholder"))
        window.resize(1200, 760)
        dialog = self.dialog(vertices=SQUARE, parent=window.fields_bar)
        self.assertEqual(dialog.height(), 760 - WINDOW_MARGIN_PX)
        self.assertIs(dialog.scroll_area.widget().parent(), dialog.scroll_area.viewport())
        # Save / Cancel are outside the scrolled part: always visible
        self.assertFalse(dialog.scroll_area.widget().isAncestorOf(dialog.save_button))
        self.assertTrue(dialog.scroll_area.widget().isAncestorOf(dialog.name_edit))


class CropSearchTest(_DialogCase):
    def test_suggestions_follow_the_language(self):
        from fieldshift.ui.field_dialog import CropSearch
        search = CropSearch()
        search.setText("peach")
        search.textEdited.emit("peach")
        self.assertEqual(search.suggestions(),
                         ["Peach – variety 1", "Peach – variety 2", "Peach – variety 3"])
        self.assertIsNone(search.selected())                      # typed, not chosen yet
        i18n.set_language("es")
        search = CropSearch()
        search.textEdited.emit("durazno")
        self.assertEqual(search.suggestions()[0], "Durazno – variedad 1")
        search.textEdited.emit("melocoton")                       # alias, no accent
        self.assertEqual(search.suggestions()[0], "Durazno – variedad 1")

    def test_choosing_from_the_dropdown_and_exact_typing(self):
        from fieldshift.ui.field_dialog import CropSearch
        search = CropSearch()
        changes = []
        search.selection_changed.connect(lambda: changes.append(search.selected()))
        search.textEdited.emit("pea")
        search._on_activated("Peach – variety 2")                  # click in the dropdown
        self.assertEqual(search.selected(), "peach.v2")
        self.assertEqual(search.text(), "Peach – variety 2")
        search.setText("Peach – variety")
        search.textEdited.emit("Peach – variety")                  # edited away: not valid
        self.assertIsNone(search.selected())
        search.setText("pear – VARIETY 1")
        search.textEdited.emit("pear – VARIETY 1")                 # exact label, any case
        self.assertEqual(search.selected(), "pear.v1")
        self.assertEqual(changes, ["peach.v2", None, "pear.v1"])

    def test_crop_is_required_and_saved(self):
        dialog = self.dialog(vertices=SQUARE, fetch=fake_fetch)
        wait_until(lambda: not dialog.is_loading())
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertFalse(dialog.crop_error.isHidden())
        dialog.crop_search.setText("xyz")
        dialog.crop_search.textEdited.emit("xyz")
        self.assertIn("No crop matches", dialog.crop_error.text())
        dialog.crop_search.choose("avocado.v1")
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertTrue(dialog.crop_error.isHidden())
        self.assertEqual(dialog.data()["crop"], {"value": "avocado.v1", "source": "user"})


class CropCatalogTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_search_ranks_and_filters(self):
        i18n.set_language("en")
        self.assertEqual(crops.search(""), [])
        self.assertEqual([v.id for v in crops.search("corn")][:1], ["maize.v1"])   # alias
        self.assertEqual([v.id for v in crops.search("peach 2")], ["peach.v2"])
        self.assertEqual([v.id for v in crops.search("Durazno")][:1], ["peach.v1"])  # other language
        self.assertLessEqual(len(crops.search("a")), crops.MAX_RESULTS)
        i18n.set_language("es")
        self.assertEqual(crops.label("maize.v3"), "Maíz – variedad 3")

    def test_ids(self):
        self.assertTrue(crops.is_variety("peach.v1"))
        for bad in ("peach.v0", "peach.v4", "peach", "nope.v1", None, 3):
            self.assertFalse(crops.is_variety(bad), bad)


class ZoneDataTest(unittest.TestCase):
    def test_usda_texture(self):
        t = zone_data.usda_texture
        self.assertEqual(t(90, 5, 5), "sand")
        self.assertEqual(t(40, 40, 20), "loam")
        self.assertEqual(t(10, 70, 20), "silt_loam")
        self.assertEqual(t(5, 88, 7), "silt")
        self.assertEqual(t(20, 20, 60), "clay")
        self.assertEqual(t(5, 50, 45), "silty_clay")
        self.assertEqual(t(30, 35, 35), "clay_loam")
        self.assertEqual(t(60, 10, 30), "sandy_clay_loam")
        self.assertEqual(t(48, 29, 23), "loam")
        self.assertEqual(t(65, 25, 10), "sandy_loam")

    def test_area_of_polygon(self):
        from fieldshift.fields import polygon_area_ha
        area = zone_data.area_of(SQUARE)
        self.assertAlmostEqual(area.lon, -70.695)
        self.assertAlmostEqual(area.lat, -33.405)
        self.assertAlmostEqual(3.14159 * area.radius_m ** 2 / 10_000,
                               polygon_area_ha(SQUARE), delta=1)

    def test_soil_extraction_and_cache(self):
        from fieldshift.api.models import Measurement
        zone_data.clear_cache()
        self.addCleanup(zone_data.clear_cache)
        group = next(g for g in zone_data.SOURCE_GROUPS if g.name == "soilgrids")
        calls = []

        class FakeProvider:
            def check(self):
                pass

            def fetch(self, area, period, site):
                calls.append(1)
                m = lambda v: Measurement(v, "", "sg")         # noqa: E731
                for depth in zone_data.TOPSOIL:
                    site.soil.sand[depth], site.soil.silt[depth] = m(40), m(40)
                    site.soil.clay[depth], site.soil.ph[depth] = m(20), m(6.0)
                site.soil.ph["0-5cm"] = m(7.5)                 # 5 of 30 cm
                site.soil.field_capacity["0-5cm"] = m(30)
                site.soil.wilting_point["0-5cm"] = m(12)
                site.soil.type = m("Luvisols")

        group = zone_data.SourceGroup(group.name, group.keys, FakeProvider, group.extract)
        area = zone_data.area_of(SQUARE)
        values = zone_data.fetch_group(group, area)
        self.assertEqual(values["soil_texture"], "loam")
        self.assertEqual(values["soil_group"], "luvisols")
        self.assertAlmostEqual(values["ph"], 6.2)              # depth-weighted, 1 decimal
        self.assertAlmostEqual(values["available_water"], 18.0)
        self.assertIsNone(values["cec"])
        zone_data.fetch_group(group, area)
        self.assertEqual(len(calls), 1)                        # second time from the cache


if __name__ == "__main__":
    unittest.main()
