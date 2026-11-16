"""Example Trends reports: made-up but plausible seasonal numbers, the same
for the same field. Used offline (tests) and when NASA POWER fails.
"""

import math
import random
import zlib
from datetime import date

from fieldshift.trends.build import make_report, measured_series


def _months(today):
    out = []
    year, month = today.year, today.month
    for _ in range(12):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        out.append(f"{year:04d}-{month:02d}")
    return tuple(reversed(out))


# (Field field, str crop = None, date today = None)
def example_report(field, crop=None, today=None):
    months = _months(today or date.today())
    lat = sum(v[1] for v in field.vertices) / len(field.vertices)
    rng = random.Random(zlib.crc32(field.name.encode()))
    hemi = 1 if lat < 0 else -1

    def warmth(m):                      # 1 in the warmest month, -1 in the coldest
        return hemi * math.cos((int(m[5:7]) - 1) / 12 * math.tau)

    def make(shift):
        s = {}
        s["temp_max"] = [24 + 7 * warmth(m) + rng.gauss(0, 1) + shift for m in months]
        s["temp_min"] = [t - 12 + rng.gauss(0, 0.8) for t in s["temp_max"]]
        s["rain"] = [max(0.0, 60 - 50 * warmth(m) + rng.gauss(0, 15)) for m in months]
        s["humidity"] = [60 - 12 * warmth(m) + rng.gauss(0, 3) for m in months]
        s["radiation"] = [19 + 8 * warmth(m) + rng.gauss(0, 1) for m in months]
        s["et0"] = [r * 4.5 for r in s["radiation"]]
        s["soil_moisture"] = [55 - 20 * warmth(m) + rng.gauss(0, 4) for m in months]
        s["soil_temp"] = [(a + b) / 2 + 1.5 for a, b in zip(s["temp_max"], s["temp_min"])]
        s["water_balance"] = [r - e for r, e in zip(s["rain"], s["et0"])]
        s["ndvi"] = [0.55 + 0.2 * warmth(m) + rng.gauss(0, 0.03) for m in months]
        return s
    series, previous = make(0.0), make(-0.4)
    previous.pop("ndvi")
    normal = {k: [v + rng.gauss(0, 0.5) for v in series[k]]
              for k in ("humidity", "radiation")}
    normal["rain"] = [max(0.0, 60 - 50 * warmth(m)) for m in months]
    sources = {k: "NASA POWER" for k in series}
    sources["ndvi"] = "MODIS"
    return make_report(field.name, months, lat, series, previous, normal, sources,
                       {"frost_days": rng.randint(0, 12), "heavy_rain_days": rng.randint(1, 8)},
                       crop=crop, example=True,
                       measured=measured_series(field.records, months))
