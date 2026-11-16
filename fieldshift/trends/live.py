"""The Trends report of a field from the real sources: two years of NASA
POWER daily values (grouped by month), its long-term normals and one year of
MODIS NDVI composites. Slow (up to a minute): run it outside the UI thread.
"""

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fieldshift.api.errors import NO_DATA, DataError, classify
from fieldshift.status import sources
from fieldshift.trends.build import make_report, measured_series

# a month counts when it has at least this many days of data
MIN_DAYS = 20
# POWER parameter (and scale) of each monthly row; None: computed
_DAILY = {"temp_max": ("T2M_MAX", 1), "temp_min": ("T2M_MIN", 1), "rain": ("PRECTOTCORR", 1),
          "humidity": ("RH2M", 1), "radiation": ("ALLSKY_SFC_SW_DWN", 1),
          "soil_moisture": ("GWETTOP", 100), "soil_temp": ("TS", 1)}
_SUMS = ("rain", "et0", "water_balance")
# normals (POWER's monthly T2M_MAX / T2M_MIN normals are extremes, not the
# mean daily max / min, so temperatures have no normal)
_CLIMATE = {"rain": "PRECTOTCORR", "humidity": "RH2M", "radiation": "ALLSKY_SFC_SW_DWN"}


def _centroid(field):
    lon = sum(v[0] for v in field.vertices) / len(field.vertices)
    lat = sum(v[1] for v in field.vertices) / len(field.vertices)
    return lon, lat


def _by_month(pairs):
    out = {}
    for day, value in pairs:
        out.setdefault(day[:7], []).append(value)
    return out


def _shift(month, years):
    return f"{int(month[:4]) + years:04d}{month[4:]}"


# (Field field, str crop = None)
# the TrendsReport of the last 12 complete months; raises api.errors.DataError
# when NASA POWER does not answer (the other sources go to report.missing)
def live_report(field, crop=None):
    lon, lat = _centroid(field)
    today = sources.today()
    first = date(today.year - 2, today.month, 1)
    missing = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        daily_job = pool.submit(sources.power_daily, lon, lat, first, today)
        climate_job = pool.submit(sources.power_climatology, lon, lat)
        ndvi_job = pool.submit(sources.modis_ndvi, lon, lat,
                               date(today.year - 1, today.month, 1) - timedelta(days=16), today)
        try:
            daily = daily_job.result()
        except Exception as exc:
            raise classify(exc, "NASA POWER") from exc
        try:
            climate = climate_job.result()
        except Exception as exc:
            climate, _ = {}, missing.append(classify(exc, "NASA POWER (normals)"))
        try:
            ndvi = ndvi_job.result()
        except Exception as exc:
            ndvi, _ = [], missing.append(classify(exc, "MODIS"))

    monthly = {key: _by_month([(d, v * scale) for d, v in daily.get(param, [])])
               for key, (param, scale) in _DAILY.items()}
    tmean = dict(daily.get("T2M", []))
    monthly["et0"] = _by_month([(d, sources.et0(tmean[d], r))
                                for d, r in daily.get("ALLSKY_SFC_SW_DWN", []) if d in tmean])
    complete = sorted(m for m, vals in monthly["temp_max"].items() if len(vals) >= MIN_DAYS)
    months = complete[-12:]
    if len(months) < 6:
        raise DataError(NO_DATA, "NASA POWER")

    def value(key, month):
        vals = monthly[key].get(month)
        if not vals or len(vals) < MIN_DAYS:
            return None
        return sum(vals) if key in _SUMS else sum(vals) / len(vals)

    def balance(month):
        rain, et = value("rain", month), value("et0", month)
        return None if None in (rain, et) else rain - et

    series = {key: [value(key, m) for m in months] for key in monthly}
    series["water_balance"] = [balance(m) for m in months]
    previous = {key: [value(key, _shift(m, -1)) for m in months] for key in monthly}
    previous["water_balance"] = [balance(_shift(m, -1)) for m in months]
    ndvi_months = _by_month(ndvi)
    series["ndvi"] = [sum(v) / len(v) if (v := ndvi_months.get(m)) else None for m in months]

    normal = {}
    for key, param in _CLIMATE.items():
        if param in climate:
            normal[key] = [climate[param][int(m[5:7]) - 1]
                           * (calendar.monthrange(int(m[:4]), int(m[5:7]))[1]
                              if key == "rain" else 1) for m in months]

    last_year = [d for d, _ in daily.get("T2M_MIN", []) if d[:7] in months]
    tmin = dict(daily.get("T2M_MIN", []))
    rain = dict(daily.get("PRECTOTCORR", []))
    counts = {"frost_days": sum(tmin[d] <= 0 for d in last_year),
              "heavy_rain_days": sum(rain.get(d, 0) >= 20 for d in last_year)}
    names = {key: "NASA POWER" for key in monthly}
    names.update(et0="NASA POWER (Hargreaves)", water_balance="NASA POWER",
                 ndvi="MODIS")
    return make_report(field.name, months, lat, series, previous, normal, names, counts,
                       crop=crop, missing=missing,
                       measured=measured_series(field.records, months))
