"""Field Shift climate scenarios on the WOFOST (PCSE) simulation, the units
the weather reaches PCSE in, and the Chilean cultivar names (no network:
synthetic weather for a field in the Maipo Valley)."""

import datetime as dt
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import crops, i18n  # noqa: E402
from fieldshift.fields import FieldStore  # noqa: E402
from fieldshift.simulation import weather  # noqa: E402
from fieldshift.simulation.scenario import (  # noqa: E402
    FIELD_SHIFT, Scenario, rdi_doses, shifted_series)
from test_simulation import HAS_PCSE, SOIL, synthetic_weather  # noqa: E402

# a field in the Maipo Valley (lon -70.65, lat -33.70)
MAIPO = [(-70.655, -33.705), (-70.645, -33.705), (-70.645, -33.695), (-70.655, -33.695)]


class WeatherUnitsTest(unittest.TestCase):

    def test_open_meteo_rain_reaches_pcse_in_cm(self):
        today = dt.date(2026, 11, 15)
        response = {"daily": {"time": ["2026-11-10"], "temperature_2m_max": [28.0],
                              "temperature_2m_min": [9.0], "precipitation_sum": [12.0],
                              "shortwave_radiation_sum": [25.0], "wind_speed_10m_mean": [10.0],
                              "dew_point_2m_mean": [5.0]}}
        day = weather.parse_open_meteo(response, today)[0]
        self.assertAlmostEqual(day.rain, 1.2)                  # 12 mm -> 1.2 cm/day
        self.assertAlmostEqual(day.irrad, 25e6)                # MJ/m² -> J/m²
        self.assertAlmostEqual(day.wind, 10 * weather.WIND_10M_TO_2M)   # at 10 m -> at 2 m


class ScenarioTest(unittest.TestCase):

    def test_shift_warms_dries_and_keeps_humidity(self):
        series = synthetic_weather(-33.7, -70.65, dt.date(2026, 10, 1), dt.date(2026, 10, 3))
        warmer = shifted_series(series, Scenario(temp_offset_c=2.0, rain_scale=0.5))
        for date, day in series.days.items():
            new = warmer.days[date]
            self.assertAlmostEqual(new.tmax, day.tmax + 2)
            self.assertAlmostEqual(new.rain, day.rain * 0.5)
            self.assertAlmostEqual(new.vap / day.vap, 1.07 ** 2, places=3)
        self.assertEqual(series.days[dt.date(2026, 10, 1)].tmax,
                         synthetic_weather(-33.7, -70.65, dt.date(2026, 10, 1),
                                           dt.date(2026, 10, 1)).days[dt.date(2026, 10, 1)].tmax)

    def test_deficit_irrigation_doses(self):
        doses = rdi_doses(FIELD_SHIFT, 100)
        self.assertEqual(doses[0], (30, 2.0))
        self.assertEqual([d for d, _ in doses], [30, 44, 58, 72, 86])


@unittest.skipUnless(HAS_PCSE, "PCSE not installed")
class MaipoScenarioTest(unittest.TestCase):

    def setUp(self):
        self.store = FieldStore(tempfile.mkdtemp())

    def test_maize_in_the_maipo_valley(self):
        from fieldshift.analysis.climate_shift import run_climate_shift
        from fieldshift.simulation.scenario import run_scenario
        field = self.store.create("Maipo", MAIPO, data={**SOIL, "crop": {"value": "maize.v1",
                                                                         "source": "user"}})
        today = dt.date(2026, 11, 15)
        baseline, shifted, rdi = run_scenario(field, today=today,
                                              build_weather=synthetic_weather)
        self.assertEqual(baseline.sowing, shifted.sowing)
        self.assertIsNotNone(rdi)                               # rain-fed: third run
        self.assertTrue(all(r.get("RFTRA") is None or 0 <= r["RFTRA"] <= 1
                            for r in shifted.output))
        self.assertGreaterEqual(rdi.summary["TWSO"], shifted.summary["TWSO"] - 1)

        result = run_climate_shift(field, run=lambda f, s: (baseline, shifted, rdi))
        labels = [m.label_key.rsplit(".", 1)[1] for m in result.metrics]
        self.assertEqual(labels[:4], ["scenario", "yield_now", "yield_shift", "change"])
        self.assertIn("yield_rdi", labels)
        self.assertEqual(result.series.unit, "t/ha")

    def test_perennial_gets_the_shift_on_climate_indices(self):
        import fake_sources
        from fieldshift.analysis.climate_shift import run_climate_shift
        restore = fake_sources.install()
        self.addCleanup(restore)
        field = self.store.create("Viña", MAIPO, data={"crop": {"value": "wine_grape.v1",
                                                                "source": "user"}})
        result = run_climate_shift(field)
        self.assertEqual(result.summary_key, "analysis.climate_shift.summary_indices")
        values = {m.label_key.rsplit(".", 1)[1]: m.value for m in result.metrics}
        now, shifted = (float(v) for v in values["gdd"].split(" (")[0].split(" → "))
        self.assertGreater(shifted, now)                     # +2 °C: more heat
        self.assertIn("(", values["gdd"])                    # Winkler region for grapes
        self.assertEqual(result.series.unit, "°C·d")


class CultivarTest(unittest.TestCase):

    def test_chilean_cultivars(self):
        i18n.set_language("es")
        self.assertEqual(crops.label("wine_grape.v1"), "Uva vinífera – Cabernet Sauvignon")
        self.assertEqual(crops.variety_name("wine_grape.v4"), "Sauvignon Blanc")
        self.assertIsNone(crops.variety_name("walnut.v3"))     # kept, still numbered
        self.assertEqual([v.id for v in crops.search("carmen")], ["wine_grape.v2"])
        self.assertEqual(crops.search("lapins")[0].id, "cherry.v2")
        i18n.set_language("en")
