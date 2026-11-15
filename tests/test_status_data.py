"""Status warning rules and the Trends report builder (pure data, no network)."""

import unittest

from fieldshift.api.forecast import DayForecast, Forecast
from fieldshift.status import rules
from fieldshift.trends.build import make_report, season_of


class RulesTest(unittest.TestCase):

    def test_observed_and_upcoming(self):
        levels, alerts = rules.observed({"rain": [0, 32, 1], "soil_moisture": [50, 25],
                                         "ndvi": [0.7, 0.6], "temp_min": [3, -1]})
        keys = {a.text_key.rsplit(".", 1)[1] for a in alerts}
        self.assertEqual(keys, {"heavy_rain", "dry_soil", "ndvi_drop", "frost"})
        self.assertEqual(levels["soil_moisture"], "alert")
        days = tuple(DayForecast(f"2026-11-{15 + i}", 5, 20, 0, "clear") for i in range(7))
        days = days[:2] + (DayForecast("2026-11-17", -2, 12, 25, "rain"),) + days[3:]
        coming = rules.upcoming(Forecast(0, 0, 0, 10, 5, "clear", days))
        self.assertEqual([a.text_key for a in coming],
                         ["status.alert.rain_upcoming", "status.alert.frost_upcoming"])
        self.assertTrue(all(a.upcoming for a in coming))


class TrendsBuildTest(unittest.TestCase):

    def test_rows_milestones_seasons(self):
        months = tuple(f"2025-{m:02d}" for m in range(1, 13))
        rain = [10.0 * m for m in range(1, 13)]
        report = make_report("A", months, -33.0, {"rain": rain, "temp_max": [20.0] * 12},
                             {"rain": [5.0] * 12}, {"rain": [60.0] * 12}, {}, {"frost_days": 3})
        row = report.section("weather").rows[1]
        self.assertEqual((row.key, row.total(), row.previous_total()), ("rain", 780, 60))
        wettest = report.milestones[0]
        self.assertEqual((wettest.value, wettest.month), ("120 mm", "2025-12"))
        self.assertEqual(season_of("2025-01", -33), "summer")
        self.assertEqual(season_of("2025-01", 40), "winter")
        self.assertEqual(report.seasons[0].name_key, "trends.season.summer")
