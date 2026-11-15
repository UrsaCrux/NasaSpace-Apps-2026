"""Tests for the place search: the geocoding API and the search panel (no network)."""

import os
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.api import geocode  # noqa: E402
from fieldshift.map import create_map_view  # noqa: E402
from qt_app import get_app  # noqa: E402

# trimmed real answers of Nominatim (boundingbox = south, north, west, east)
CITY = [{"display_name": "Melipilla, Región Metropolitana, Chile", "lon": "-71.2", "lat": "-33.69",
         "boundingbox": ["-33.75", "-33.65", "-71.25", "-71.15"], "type": "administrative"}]
HOUSE = [{"display_name": "Casa Central, Avenida Libertador Bernardo O'Higgins 1058, Santiago",
          "lon": "-70.6509", "lat": "-33.4445",
          "boundingbox": ["-33.4448965", "-33.4442215", "-70.6514443", "-70.6504662"],
          "type": "university"}, {"broken": True}]


def setUpModule():
    get_app()


class GeocodeTest(unittest.TestCase):
    def setUp(self):
        geocode.clear_cache()
        self.addCleanup(geocode.clear_cache)

    def test_parse_skips_unreadable_items(self):
        places = geocode.parse_places(HOUSE)
        self.assertEqual(len(places), 1)
        p = places[0]
        self.assertEqual((p.lon, p.lat), (-70.6509, -33.4445))
        self.assertEqual(p.bbox, (-70.6514443, -33.4448965, -70.6504662, -33.4442215))  # x, y order

    def test_short_text_makes_no_request(self):
        with mock.patch.object(geocode, "_request") as request:
            self.assertEqual(geocode.search(" a "), [])
        request.assert_not_called()

    def test_chile_first_then_the_world_and_cache(self):
        calls = []

        def fake(text, country):
            calls.append(country)
            return [] if country == "cl" else CITY
        with mock.patch.object(geocode, "_request", side_effect=fake):
            self.assertEqual(len(geocode.search("Paris")), 1)         # nothing in Chile
            self.assertEqual(calls, ["cl", None])
            geocode.search("  PARIS ")                                # cached: same text
        self.assertEqual(len(calls), 2)

    def test_found_in_chile_does_not_search_the_world(self):
        calls = []
        with mock.patch.object(geocode, "_request",
                               side_effect=lambda t, c: calls.append(c) or CITY):
            geocode.search("Melipilla")
        self.assertEqual(calls, ["cl"])

    def test_zone_name_from_a_reverse_answer(self):
        self.assertEqual(geocode.parse_zone({"address": {"county": "X", "town": "Melipilla"}}),
                         "Melipilla")
        self.assertIsNone(geocode.parse_zone({"error": "Unable to geocode"}))
        answer = {"address": {"city": "Santiago", "state": "RM"}}
        with mock.patch.object(geocode, "_get", return_value=answer) as get:
            self.assertEqual(geocode.zone_name(-70.62, -33.42), "Santiago")
            self.assertEqual(geocode.zone_name(-70.63, -33.43), "Santiago")   # same cell: cached
        self.assertEqual(get.call_count, 1)

    def test_requests_are_spaced_and_identified(self):
        sleeps, sent = [], {}

        class Answer:
            def raise_for_status(self): pass
            def json(self): return CITY

        def fake_get(url, params, headers, timeout):
            sent.update(headers=headers, params=params)
            return Answer()
        with mock.patch("requests.get", side_effect=fake_get), \
                mock.patch.object(geocode.time, "sleep", side_effect=sleeps.append):
            geocode.clear_cache()
            geocode._request("a", "cl")
            geocode._request("b", None)                               # right after: must wait
        self.assertEqual(len(sleeps), 1)
        self.assertGreater(sleeps[0], 0.5)
        self.assertTrue(sent["headers"]["User-Agent"].startswith("FieldShift/"))
        self.assertNotIn("countrycodes", sent["params"])


class MapSearchTest(unittest.TestCase):
    def setUp(self):
        from fieldshift.ui import MainWindow
        from fieldshift.ui.map_search import MapSearch
        i18n.set_language("en")
        self.view = create_map_view("placeholder")
        self.window = MainWindow(self.view)
        self.answer = list(geocode.parse_places(CITY))
        self.searched = []

        def fake(text):
            self.searched.append(text)
            if self.answer is None:
                raise OSError("no network")
            return self.answer
        self.search = MapSearch(self.view, self.window.map_controls, search=fake)

    def run_search(self, text):
        self.search.edit.setText(text)
        started = self.search.search()
        for thread in [t for t in threading.enumerate() if t.name == "map-search"]:
            thread.join(5)
        get_app().processEvents()
        return started

    def test_button_opens_and_closes_the_panel(self):
        button = self.window.map_controls.search_button
        self.assertTrue(self.search.isHidden())
        button.click()
        self.assertFalse(self.search.isHidden())
        self.assertIn("OpenStreetMap", self.search.credit_label.text())
        self.search.keyPressEvent(__import__("PyQt6.QtGui", fromlist=["QKeyEvent"]).QKeyEvent(
            __import__("PyQt6.QtCore", fromlist=["QEvent"]).QEvent.Type.KeyPress,
            __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Escape,
            __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.KeyboardModifier.NoModifier))
        self.assertTrue(self.search.isHidden())
        self.assertFalse(button.isChecked())

    def test_search_lists_results_and_a_click_goes_there(self):
        self.window.map_controls.search_button.click()
        self.assertTrue(self.run_search("Melipilla"))
        self.assertEqual(self.search.results.count(), 1)
        self.assertEqual(self.search.results.item(0).text(), "Melipilla, Región Metropolitana, Chile")
        with mock.patch.object(self.view, "zoom_to_extent") as zoom:
            self.search.results.itemClicked.emit(self.search.results.item(0))
        xmin, ymin, xmax, ymax = zoom.call_args.args
        self.assertTrue(xmin < -71.25 and xmax > -71.15 and ymin < -33.75 and ymax > -33.65)
        self.assertEqual(self.view.pin(), (-71.2, -33.69))
        # the panel closes by itself; the pin stays with a chip to remove it
        self.assertTrue(self.search.isHidden())
        self.assertFalse(self.window.map_controls.search_button.isChecked())
        self.assertFalse(self.search.chip.isHidden())
        self.assertEqual(self.search.chip.label.text(), "📍 Melipilla")

    def test_long_names_are_not_cut_off(self):
        long_name = ("Casa Central Universidad de Chile, 1058, Avenida Libertador Bernardo O'Higgins, "
                     "Santiago, Provincia de Santiago, Región Metropolitana de Santiago, 8320000, Chile")
        self.answer = [geocode.Place(long_name, -70.65, -33.44, (-70.66, -33.45, -70.64, -33.43))]
        self.window.map_controls.search_button.click()
        self.run_search("Casa Central")
        row_height = self.search.results.fontMetrics().height()
        self.assertGreater(self.search.results.height(), 3 * row_height)    # several lines fit

    def test_an_address_is_zoomed_with_surroundings(self):
        from fieldshift.ui.map_search import MIN_HALF_SPAN_DEG, padded_bbox
        place = geocode.parse_places(HOUSE)[0]
        xmin, ymin, xmax, ymax = padded_bbox(place.bbox)
        self.assertGreaterEqual((xmax - xmin) / 2, MIN_HALF_SPAN_DEG - 1e-9)   # not just the house
        self.assertGreaterEqual((ymax - ymin) / 2, MIN_HALF_SPAN_DEG - 1e-9)
        self.assertLess(xmin, place.bbox[0])

    def test_enter_searches_and_then_goes_to_the_first_result(self):
        self.window.map_controls.search_button.click()
        self.run_search("Melipilla")
        self.search.edit.returnPressed.emit()                  # same text: go to the first
        self.assertEqual(self.view.pin(), (-71.2, -33.69))
        self.assertEqual(self.searched, ["Melipilla"])         # no second search

    def test_nothing_found_and_failure_messages(self):
        self.answer = []
        self.run_search("zzzzzz")
        self.assertEqual(self.search.status_label.text(), "Nothing found for “zzzzzz”")
        self.answer = None
        self.run_search("Melipilla")
        self.assertEqual(self.search.status_label.text(), "Could not search (check your connection)")
        self.assertIsNone(self.view.pin())

    def test_chip_cross_removes_the_pin(self):
        self.window.map_controls.search_button.click()
        self.run_search("Melipilla")
        self.search.go_to(0)
        self.assertIsNotNone(self.view.pin())
        self.search.chip.close_button.click()
        self.assertIsNone(self.view.pin())
        self.assertTrue(self.search.chip.isHidden())

    def test_pin_goes_away_when_drawing_starts_or_a_new_search_opens(self):
        for leave in (lambda: self.window.fields_bar.draw_button.click(),
                      lambda: self.window.map_controls.search_button.click()):
            self.window.map_controls.search_button.setChecked(True)
            self.run_search("Melipilla")
            self.search.go_to(0)
            self.assertIsNotNone(self.view.pin())
            leave()
            self.assertIsNone(self.view.pin())
            self.assertTrue(self.search.chip.isHidden())
            self.view.cancel_drawing()
            self.window.map_controls.search_button.setChecked(False)

    def test_closing_the_panel_keeps_the_pin_and_drops_late_answers(self):
        self.window.map_controls.search_button.click()
        self.run_search("Melipilla")
        self.search.go_to(0)
        self.assertIsNotNone(self.view.pin())                   # panel closed by go_to
        self.search._on_finished(self.search._request - 1, list(geocode.parse_places(CITY)))
        self.assertEqual(self.search.places, [])               # stale answer dropped

    def test_offline_says_not_available(self):
        from fieldshift.ui.map_search import MapSearch
        with mock.patch.dict(os.environ, {"FIELDSHIFT_OFFLINE": "1"}):
            panel = MapSearch(self.view, self.window.map_controls)
        panel.edit.setText("Melipilla")
        self.assertFalse(panel.search())
        self.assertEqual(panel.status_label.text(), "Search not available")


if __name__ == "__main__":
    unittest.main()
