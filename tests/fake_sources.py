"""Deterministic stand-ins for fieldshift.analysis.sources (no network).

    import fake_sources
    restore = fake_sources.install()     # ... run analyses ...
    restore()
"""

import datetime as dt
import math

from fieldshift.analysis import sources
from fieldshift.crops.ecocrop import CropInfo, Range

TODAY = dt.date(2026, 11, 15)


def _season(date):
    """1 in mid-summer (January, south), 0 in mid-winter."""
    return (1 + math.cos(2 * math.pi * (date.timetuple().tm_yday - 15) / 365)) / 2


def power_daily(lon, lat, start, end):
    out = {"T2M_MIN": {}, "T2M_MAX": {}, "PRECTOTCORR": {}, "GWETROOT": {}}
    d = start
    while d <= end:
        s = _season(d)
        out["T2M_MIN"][d] = round(-3 + 14 * s + 2 * math.sin(d.toordinal()), 1)
        out["T2M_MAX"][d] = round(14 + 20 * s + 2 * math.cos(d.toordinal()), 1)
        out["PRECTOTCORR"][d] = round(max(0.0, 6 * (1 - s) - 2 + 3 * math.sin(d.toordinal() / 3)), 1)
        out["GWETROOT"][d] = 0.5
        d += dt.timedelta(days=1)
    return out


def power_climatology(lon, lat):
    keys = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    s = [(1 + math.cos(2 * math.pi * i / 12)) / 2 for i in range(12)]
    return {"T2M": dict(zip(keys, [9 + 13 * v for v in s]), ANN=15.9),
            "T2M_MIN": dict(zip(keys, [-3 + 12 * v for v in s]), ANN=-3),
            "T2M_MAX": dict(zip(keys, [26 + 14 * v for v in s]), ANN=40),
            "PRECTOTCORR": dict(zip(keys, [0.2 + 2.4 * (1 - v) for v in s]), ANN=1.0),
            "FROST_DAYS": dict(zip(keys, [max(0, 3 - 6 * v) for v in s]), ANN=6)}


def wapor_grids(mapset, field, months):
    base = 60 if "NPP" in mapset else 80
    out = {}
    for i, month in enumerate(months):
        s = _season(dt.date(int(month[:4]), int(month[5:]), 15))
        out[month] = [[round(base * (0.3 + s) * (0.8 + 0.05 * ((r + c) % 5)), 1)
                       for c in range(sources.GRID)] for r in range(sources.GRID)]
    out[months[0]] = None                          # one month not published
    return out


def dem_grid(field):
    return [[500 + 10 * r + 5 * c for c in range(sources.GRID)] for r in range(sources.GRID)]


def forecast(lon, lat):
    raise ConnectionError("no forecast in tests")


def crop_requirements_of(target):
    return CropInfo(0, str(target), temperature=Range(12, 26, 4, 34),
                    rainfall=Range(300, 800, 150, 1500), ph=Range(5.5, 7.5, 4.5, 8.5),
                    soil_texture={"optimal": "medium", "absolute": "heavy, medium, light"},
                    killing_temp_early_growth=-2, crop_cycle_min=100, crop_cycle_max=150)


def crop_requirements(field):
    value = ((field.data or {}).get("crop") or {}).get("value")
    return crop_requirements_of(value) if value else None


# ()
# replaces the sources with the fakes; returns a function that puts them back
def install():
    names = ("power_daily", "power_climatology", "wapor_grids", "dem_grid", "forecast",
             "crop_requirements_of", "crop_requirements")
    saved = {n: getattr(sources, n) for n in names}
    saved["TODAY"] = sources.TODAY
    for n in names:
        setattr(sources, n, globals()[n])
    sources.TODAY = TODAY
    sources.clear_cache()

    def restore():
        for n, v in saved.items():
            setattr(sources, n, v)
        sources.clear_cache()
    return restore
