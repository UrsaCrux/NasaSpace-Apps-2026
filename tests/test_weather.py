"""Tests for the forecast API and the weather card (no network)."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.api import forecast as api  # noqa: E402
from fieldshift.map import create_map_view  # noqa: E402
from qt_app import get_app  # noqa: E402

# trimmed real answer of Open-Meteo
ANSWER = {
    "elevation": 257.0,
    "current": {"temperature_2m": 16.2, "weather_code": 3, "wind_speed_10m": 12.0,
                "time": "2026-11-16T09:15"},
    "hourly": {"time": [f"2026-11-16T{h:02d}:00" for h in range(24)],
               "temperature_2m": [10.0 + h / 2 for h in range(24)],
               "weather_code": [0] * 24, "precipitation_probability": [h for h in range(24)]},
    "daily": {"time": ["2026-11-16", "2026-11-17", "2026-11-18"],     # Mon, Tue, Wed
              "temperature_2m_min": [5.5, -1.2, 0.0],
              "temperature_2m_max": [23.0, 19.3, 23.6],
              "precipitation_sum": [0.2, 1.4, None],
              "weather_code": [51, 0, 95]},
}


def setUpModule():
    get_app()


class ForecastApiTest(unittest.TestCase):
    def setUp(self):
        api.clear_cache()
        self.addCleanup(api.clear_cache)

    def test_parse(self):
        f = api.parse_forecast(ANSWER, -71.02, -33.73)
        self.assertEqual((f.temperature, f.wind_kmh, f.sky, f.elevation),
                         (16.2, 12.0, api.SKY_CLOUDY, 257.0))
        self.assertEqual([d.sky for d in f.days], [api.SKY_RAIN, api.SKY_CLEAR, api.SKY_STORM])
        self.assertEqual([d.date for d in f.frost_days()], ["2026-11-17", "2026-11-18"])
        self.assertAlmostEqual(f.total_rain_mm(), 1.6)           # None counts as 0

    def test_bad_answer_raises(self):
        with self.assertRaises((KeyError, TypeError, ValueError)):
            api.parse_forecast({"current": {}}, 0, 0)

    def test_one_request_per_cell(self):
        with mock.patch.object(api, "get_json", return_value=ANSWER) as get:
            a = api.get_forecast(-71.02, -33.73)
            b = api.get_forecast(-71.03, -33.74)                 # same ~10 km cell
            api.get_forecast(-71.50, -33.73)                     # another cell
        self.assertIs(a, b)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args.kwargs["params"]["forecast_days"], api.DAYS)


class WeatherCardTest(unittest.TestCase):
    def setUp(self):
        from fieldshift.ui.weather_card import WeatherCard
        i18n.set_language("en")
        self.view = create_map_view("placeholder")
        self.view.widget().resize(900, 600)
        self.calls = []
        self.answer = api.parse_forecast(ANSWER, -71.02, -33.73)

        def fetch(lon, lat):
            self.calls.append((lon, lat))
            if self.answer is None:
                raise OSError("no network")
            return self.answer
        self.card = WeatherCard(self.view, fetch=fetch)

    def load(self):
        started = self.card.reload()
        if started:
            # run the loader here instead of waiting for its thread
            for thread in [t for t in __import__("threading").enumerate()
                           if t.name == "weather-card"]:
                thread.join(5)
            get_app().processEvents()
        return started

    def test_hidden_until_the_map_has_a_centre(self):
        self.assertFalse(self.load())
        self.assertTrue(self.card.isHidden())

    def test_shows_now_hours_today_and_credit(self):
        self.view.set_center(-71.02, -33.73)
        self.assertTrue(self.load())
        self.assertFalse(self.card.isHidden())
        self.assertIn("16 °C now", self.card.now_label.text())
        hours = self.card.hours_label.text()
        for text in ("09h", "12h", "21h", "14°"):           # from the current hour, every 3
            self.assertIn(text, hours)
        self.assertNotIn("06h", hours)
        summary = self.card.summary_label.text()
        self.assertIn("Today: max 23° / min 6° · rain 0.2 mm", summary)
        self.assertIn("257 m", summary)
        self.assertIn("Open-Meteo", self.card.credit_label.text())
        # top-right corner of the map
        self.assertEqual(self.card.x() + self.card.width(), 900 - 12)

    def test_title_names_the_zone(self):
        from fieldshift.ui.weather_card import WeatherCard
        names = {"value": "Melipilla"}

        def zone(lon, lat):
            if names["value"] is None:
                raise OSError("no network")
            return names["value"]
        self.card = WeatherCard(self.view, fetch=lambda lon, lat: self.answer, zone_name=zone)
        self.view.set_center(-71.02, -33.73)
        self.load()
        self.assertEqual(self.card.title_label.text(), "<b>Weather in Melipilla</b>")
        names["value"] = None                                    # name service down
        self.view.set_center(-72.50, -36.60)
        self.load()
        self.assertEqual(self.card.title_label.text(), "<b>Weather in this zone</b>")
        self.assertIn("16 °C", self.card.now_label.text())      # the weather still shows

    def test_reloads_only_in_another_zone(self):
        self.view.set_center(-71.02, -33.73)
        self.load()
        self.view.set_center(-71.03, -33.74)                     # same cell
        self.assertFalse(self.load())
        self.view.set_center(-72.50, -36.60)
        self.assertTrue(self.load())
        self.assertEqual(len(self.calls), 2)

    def test_failure_shows_a_message_and_retries_later(self):
        self.answer = None
        self.view.set_center(-71.02, -33.73)
        self.load()
        self.assertEqual(self.card.now_label.text(), "Weather not available")
        self.assertTrue(self.card.hours_label.isHidden())
        self.answer = api.parse_forecast(ANSWER, -71.02, -33.73)
        self.assertTrue(self.load())                             # same zone: tries again
        self.assertIn("16 °C", self.card.now_label.text())

    def test_offline_card_never_loads(self):
        from fieldshift.ui.weather_card import WeatherCard
        with mock.patch.dict(os.environ, {"FIELDSHIFT_OFFLINE": "1"}):
            card = WeatherCard(self.view)
        self.view.set_center(-71.02, -33.73)
        self.assertFalse(card.reload())
        self.assertTrue(card.isHidden())


if __name__ == "__main__":
    unittest.main()
