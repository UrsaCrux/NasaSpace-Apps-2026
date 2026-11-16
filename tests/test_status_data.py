"""Status warning rules and the Trends report builder (pure data, no network)."""

import unittest

from fieldshift.api.forecast import DayForecast, Forecast
from fieldshift.status import StatusReport, Tracking, rules
from fieldshift.trends.build import make_report, season_of


class RulesTest(unittest.TestCase):

    def test_light_warnings_of_the_coming_days(self):
        def day(i, tmin, tmax, rain=0.0, wind=10.0):
            return DayForecast(f"2026-11-{15 + i:02d}", tmin, tmax, rain, "clear", wind)
        days = (day(0, 8, 20), day(1, 1, 18, rain=15), day(2, 7, 29), day(3, 9, 22, wind=50))
        alerts = rules.forecast_alerts(days)
        self.assertEqual([(a.text_key.rsplit(".", 1)[1], a.date) for a in alerts],
                         [("rain", "2026-11-16"), ("frost", "2026-11-16"),
                          ("temp_swing", "2026-11-17"), ("wind", "2026-11-18")])
        report = StatusReport("A", (), Forecast(0, 0, 0, 10, 5, "clear", days), tuple(alerts))
        self.assertEqual(len(report.alerts_within(2)), 2)

    def test_tracking_change(self):
        self.assertAlmostEqual(Tracking("Potato", 0.65, "2026-10-16", 0.5).change_pct(), 30.0)
        self.assertIsNone(Tracking("Potato", 0.65, "2026-10-16").change_pct())


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
