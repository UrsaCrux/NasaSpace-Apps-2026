"""Tests for the crop model inputs, the weather assembly, the PCSE run and
the texture / crop growth analyses (no network: weather is synthetic)."""

import datetime as dt
import importlib.util
import json
import math
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.fields import FieldStore  # noqa: E402
from fieldshift.simulation import soil, weather  # noqa: E402
from fieldshift.simulation.run import NotSimulable, season_start  # noqa: E402
from qt_app import get_app  # noqa: E402

HAS_PCSE = importlib.util.find_spec("pcse") is not None
SQUARE = [(-71.0, -34.5), (-70.99, -34.5), (-70.99, -34.51), (-71.0, -34.51)]
SOIL = {"clay": {"value": 21.0, "source": "prefilled"}, "sand": {"value": 42.0, "source": "prefilled"},
        "silt": {"value": 37.0, "source": "prefilled"},
        "soil_texture": {"value": "loam", "source": "prefilled"},
        "organic_carbon": {"value": 25.0, "source": "prefilled"}}


def setUpModule():
    get_app()


def synthetic_weather(lat, lon, start, end, today=None):
    """Mild, wet-enough weather every day (a plausible growing season)."""
    days = {}
    d = start
    while d <= end:
        doy = d.timetuple().tm_yday
        warm = 18 + 6 * math.cos(2 * math.pi * (doy - 15) / 365)   # southern summer
        days[d] = weather.Day(d, warm - 7, warm + 7, 20e6, 0.3 if doy % 3 == 0 else 0.0,
                              14.0, 2.0, weather.SOURCE_CLIMATE)
        d += dt.timedelta(days=1)
    return weather.WeatherSeries(days, ["test"], 500.0)


class SoilTest(unittest.TestCase):
    def test_saxton_rawls_matches_the_paper(self):
        # Saxton & Rawls (2006), table 3: loam (40 % sand, 20 % clay, 2.5 % OM)
        loam = soil.saxton_rawls(40, 20, 2.5)
        self.assertAlmostEqual(loam["wilting_point"], 0.12, delta=0.02)
        self.assertAlmostEqual(loam["field_capacity"], 0.28, delta=0.02)
        self.assertAlmostEqual(loam["saturation"], 0.46, delta=0.02)
        sand = soil.saxton_rawls(88, 5, 2.5)
        self.assertLess(sand["field_capacity"], 0.15)
        self.assertGreater(sand["ksat_mm_h"], loam["ksat_mm_h"])

    def test_descriptor_uses_the_fields_data(self):
        d = soil.site_descriptor({**SOIL, "available_water": {"value": 15.0},
                                  "slope": {"value": 8.0}})
        s = d["soil"]
        self.assertAlmostEqual(s["SMFCF"] - s["SMW"], 0.15, places=3)    # field's available water
        self.assertTrue(s["SMW"] < s["SMFCF"] < s["SM0"] < 1)
        self.assertEqual(d["site"]["NOTINF"], 0.08)                         # from the slope
        self.assertEqual(set(d["site"]), {"WAV", "IFUNRN", "NOTINF", "SSI", "SSMAX", "SMLIM"})

    def test_descriptor_without_fractions_uses_the_class(self):
        d = soil.site_descriptor({"soil_texture": {"value": "clay"}})
        self.assertEqual(d["inputs"]["clay_pct"], 60)
        self.assertTrue(any("typical" in a for a in d["assumptions"]))


@unittest.skipUnless(HAS_PCSE, "PCSE not installed")
class WofostCropsTest(unittest.TestCase):
    def test_mapping(self):
        from fieldshift.crops import wofost_crops as w
        maize = w.crop_info("maize.v2")
        self.assertEqual((maize["crop_name"], maize["variety_name"], maize["match"]),
                         ("maize", "Grain_maize_201", "exact"))
        self.assertIn("TSUM1", maize["parameters"])
        json.dumps(maize)                                       # storable in the file
        self.assertEqual(w.crop_info("oat.v1")["match"], "proxy")
        self.assertIsNone(w.crop_info("peach.v1"))             # no model for fruit trees
        self.assertEqual(w.crop_info("ecocrop:2175", "Zea mays")["crop_name"], "maize")


class HiddenDataTest(unittest.TestCase):
    def test_saving_stores_hidden_model_inputs(self):
        store = FieldStore(tempfile.mkdtemp())
        field = store.create("A", SQUARE, data={**SOIL, "crop": {"value": "peach.v1",
                                                                 "source": "user"}})
        data = json.loads(field.path.read_text("utf-8"))["features"][0]["properties"]["data"]
        self.assertIsNone(data["wofost"])                       # peach: no WOFOST model
        self.assertIn("SMFCF", data["pcse_site"]["soil"])
        again = store.get("A")
        self.assertEqual(again.data["pcse_site"], data["pcse_site"])     # kept on load
        if HAS_PCSE:
            store.update("A", "A", data={**SOIL, "crop": {"value": "wheat.v1", "source": "user"}})
            self.assertEqual(store.get("A").data["wofost"]["crop_name"], "wheat")

    def test_hidden_data_is_not_shown(self):
        from fieldshift.fields.schema import DATA_FIELDS
        self.assertFalse({"wofost", "pcse_site"} & {s.key for s in DATA_FIELDS})


class WeatherTest(unittest.TestCase):
    today = dt.date(2026, 11, 15)

    def test_parse_open_meteo(self):
        response = {"daily": {"time": ["2026-11-14", "2026-11-15", "2026-11-16"],
                              "temperature_2m_min": [8, 9, None],
                              "temperature_2m_max": [24, 26, 27],
                              "shortwave_radiation_sum": [25.0, 26.0, 27.0],
                              "precipitation_sum": [0.0, 5.0, 0.0],
                              "dew_point_2m_mean": [7.0, 8.0, 9.0],
                              "wind_speed_10m_mean": [3.0, 3.0, 3.0]}}
        days = weather.parse_open_meteo(response, self.today)
        self.assertEqual([d.source for d in days], ["observed", "forecast"])   # null day skipped
        d = days[1]
        self.assertEqual((d.irrad, d.rain), (26e6, 0.5))                        # J/m², cm
        self.assertAlmostEqual(d.wind, 3.0 * weather.WIND_10M_TO_2M)
        self.assertAlmostEqual(d.vap, 10.7, delta=0.1)                          # hPa at 8 °C dew

    def test_parse_power(self):
        response = {"header": {"fill_value": -999},
                    "properties": {"parameter": {
                        "T2M_MAX": {"20261101": 25, "20261102": -999},
                        "T2M_MIN": {"20261101": 9, "20261102": 10},
                        "ALLSKY_SFC_SW_DWN": {"20261101": 24, "20261102": 25},
                        "PRECTOTCORR": {"20261101": 2, "20261102": 0},
                        "T2MDEW": {"20261101": 6, "20261102": 6},
                        "WS2M": {"20261101": 2, "20261102": 2}}}}
        days = weather.parse_power(response)
        self.assertEqual(len(days), 1)
        self.assertEqual((days[0].date, days[0].rain), (dt.date(2026, 11, 1), 0.2))

    def test_fallback_and_climate_fill(self):
        def fail(*a):
            raise ConnectionError("rate limited")

        def power(lat, lon, start, end):
            out, d = [], start
            while d <= end:
                out.append(weather.Day(d, 5, 20, 15e6, 0.1, 10, 2))
                d += dt.timedelta(days=1)
            return out
        series = weather.build_weather(-34.5, -71.0, dt.date(2026, 10, 15), dt.date(2027, 3, 1),
                                       self.today, open_meteo=fail, power=power)
        self.assertEqual(series.providers, ["NASA POWER"])
        counts = series.counts()
        self.assertEqual(counts["observed"], 32)                  # 15 Oct .. 15 Nov
        self.assertEqual(counts["climate"], len(series.days) - 32)
        self.assertEqual(sum(counts.values()), (dt.date(2027, 3, 1) - dt.date(2026, 10, 15)).days + 1)
        with self.assertRaises(RuntimeError):
            weather.build_weather(-34.5, -71.0, self.today, self.today, self.today,
                                  open_meteo=fail, power=fail)

    def test_season_start(self):
        sowing, in_season = season_start((10, 15), -34.5, dt.date(2026, 11, 15))
        self.assertEqual((sowing, in_season), (dt.date(2026, 10, 15), True))
        sowing, in_season = season_start((5, 15), -34.5, dt.date(2026, 11, 15))
        self.assertEqual((sowing, in_season), (dt.date(2027, 5, 15), False))
        sowing, _ = season_start((10, 15), 45.0, dt.date(2026, 11, 15))      # north: April
        self.assertEqual(sowing, dt.date(2027, 4, 15))


@unittest.skipUnless(HAS_PCSE, "PCSE not installed")
class SimulationTest(unittest.TestCase):
    def setUp(self):
        self.store = FieldStore(tempfile.mkdtemp())

    def test_runs_the_season(self):
        from fieldshift.simulation.run import simulate
        field = self.store.create("A", SQUARE, data={**SOIL, "crop": {"value": "maize.v1",
                                                                      "source": "user"}})
        sim = simulate(field, today=dt.date(2026, 11, 15), build_weather=synthetic_weather)
        self.assertEqual((sim.crop_name, sim.sowing, sim.in_season),
                         ("maize", dt.date(2026, 10, 15), True))
        self.assertFalse(sim.irrigated)
        self.assertGreater(max(r["LAI"] or 0 for r in sim.output), 1)
        self.assertGreater(sim.summary["TAGP"], 1000)
        potential = simulate(field, today=dt.date(2026, 11, 15), potential=True,
                             series=sim.series)
        self.assertGreaterEqual(potential.summary["TWSO"], sim.summary["TWSO"] - 1)

    def test_not_simulable(self):
        from fieldshift.simulation.run import simulate
        no_crop = self.store.create("B", SQUARE, data=SOIL)
        with self.assertRaises(NotSimulable):
            simulate(no_crop, build_weather=synthetic_weather)
        peach = self.store.create("C", SQUARE, data={"crop": {"value": "peach.v1",
                                                              "source": "user"}})
        with self.assertRaisesRegex(NotSimulable, "no_model"):
            simulate(peach, build_weather=synthetic_weather)


class AnalysesTest(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")
        self.store = FieldStore(tempfile.mkdtemp())

    def test_texture(self):
        from fieldshift.analysis.texture import run_texture
        result = run_texture(self.store.create("A", SQUARE, data=SOIL))
        self.assertIsNone(result.series)
        self.assertEqual((result.figure.texture, result.figure.clay), ("loam", 21.0))
        self.assertFalse(result.placeholder)
        empty = run_texture(self.store.create("B", SQUARE))
        self.assertEqual(empty.summary_key, "analysis.texture.summary_unknown")

    @unittest.skipUnless(HAS_PCSE, "PCSE not installed")
    def test_crop_growth(self):
        from fieldshift.analysis.crop_growth import run_crop_growth
        from fieldshift.simulation import run as run_mod
        field = self.store.create("A", SQUARE, data={**SOIL, "crop": {"value": "wheat.v1",
                                                                      "source": "user"}})

        def simulate(f, potential=None, series=None):
            return run_mod.simulate(f, today=dt.date(2026, 11, 15), potential=potential,
                                    series=series, build_weather=synthetic_weather)
        result = run_crop_growth(field, simulate=simulate)
        self.assertEqual(len(result.series.dates), len(result.frames.grids))
        self.assertEqual(len(result.series.dates[0]), 10)                     # daily
        self.assertEqual(result.summary_key, "analysis.crop_growth.summary_next")
        labels = [m.label_key.rsplit(".", 1)[-1] for m in result.metrics]
        self.assertEqual(labels[:2], ["yield", "potential"])
        no_crop = run_crop_growth(self.store.create("B", SQUARE))
        self.assertEqual(no_crop.summary_key, "analysis.crop_growth.summary_no_crop")
        self.assertIsNone(no_crop.series)

    def test_tab_shows_the_triangle_instead_of_chart_and_map(self):
        from fieldshift.analysis.texture import run_texture
        from fieldshift.ui.analysis_tab import AnalysisTab
        from fieldshift.ui.analysis_widgets import TextureTriangle
        field = self.store.create("A", SQUARE, data=SOIL)
        tab = AnalysisTab(run_texture(field), field)
        self.assertIsInstance(tab.figure, TextureTriangle)
        self.assertFalse(hasattr(tab, "preview"))
        tab.set_date_index(3)                                  # no time line: nothing happens
        tab.set_playing(True)
        tab.figure.resize(500, 420)
        inside = tab.figure.point(42, 21)                      # the field's point is drawn
        self.assertTrue(tab.figure.rect().contains(inside.toPoint()))
        self.assertLess(tab.figure.point(0, 100).y(), tab.figure.point(100, 0).y())  # clay on top

    def test_daily_dates(self):
        from fieldshift.ui.analysis_widgets import format_date
        self.assertEqual(format_date("2026-12-07"), "7 December 2026")
        self.assertEqual(format_date("2026-12"), "December 2026")


if __name__ == "__main__":
    unittest.main()
