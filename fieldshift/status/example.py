"""Example Status reports: made-up but plausible weather for today and the
next 16 days, the same for the same field. Used offline (tests) and when the
forecast service fails.
"""

import random
import zlib
from datetime import date, timedelta

from fieldshift.status import rules
from fieldshift.status.build import today_tiles
from fieldshift.status.models import FORECAST_DAYS, StatusReport, Tracking


# (Field field, date today = None)
# an example api.forecast.Forecast (days and today's hours)
def example_forecast(field, today=None):
    from fieldshift.api.forecast import (
        SKY_CLEAR, SKY_PARTLY, SKY_RAIN, DayForecast, Forecast, HourForecast)
    today = today or date.today()
    rng = random.Random(zlib.crc32(field.name.encode()))
    days = []
    for i in range(FORECAST_DAYS):
        tmax = rng.uniform(18, 27) + (9 if i == 5 else 0)          # a warm jump
        tmin = rng.uniform(-1, 1.5) if i == 3 else rng.uniform(5, 11)
        rain = rng.uniform(12, 28) if i == 1 else (rng.uniform(0, 4) if rng.random() < 0.3 else 0)
        sky = SKY_RAIN if rain > 5 else (SKY_PARTLY if rain else SKY_CLEAR)
        days.append(DayForecast(
            (today + timedelta(days=i)).isoformat(), round(tmin, 1), round(tmax, 1),
            round(rain, 1), sky, round(rng.uniform(8, 30)), round(rng.uniform(40, 85)),
            round(rng.uniform(14, 30), 1), round(min(100, rain * 4 + rng.uniform(0, 20))),
            round(rng.uniform(4, 10), 1), round(rng.uniform(2, 6), 1)))
    first = days[0]
    hours = tuple(HourForecast(f"{first.date}T{h:02d}:00",
                               round(first.tmin + (first.tmax - first.tmin)
                                     * max(0.0, 1 - abs(h - 15) / 10), 1),
                               SKY_PARTLY if 9 <= h <= 18 else SKY_CLEAR,
                               round(rng.uniform(0, 30)), round(rng.uniform(5, 20)),
                               round(rng.uniform(18, 32), 1), round(rng.uniform(12, 24), 1))
                  for h in range(24))
    return Forecast(0.0, 0.0, 0.0, round((first.tmax + first.tmin) / 2, 1), 12.0, first.sky,
                    tuple(days), 60.0, f"{first.date}T12:00", hours)


# (Field field, date today = None)
def example_report(field, today=None):
    coming = example_forecast(field, today)
    return StatusReport(field.name, today_tiles(coming), coming,
                        tuple(rules.forecast_alerts(coming.days)), example=True)


# (Field field, str crop, date today = None)
def example_tracking(field, crop, today=None):
    today = today or date.today()
    rng = random.Random(zlib.crc32(f"{field.name}|ndvi".encode()))
    previous = rng.uniform(0.4, 0.55)
    return Tracking(crop, round(previous * rng.uniform(1.05, 1.35), 2),
                    (today - timedelta(days=30)).isoformat(), round(previous, 2),
                    (today - timedelta(days=46)).isoformat())
