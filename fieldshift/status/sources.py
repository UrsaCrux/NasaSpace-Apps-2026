"""Satellite time series for Status and Trends, one value per day (NASA
POWER) or per 16-day composite (MODIS NDVI). Plain data, no Qt.

NASA POWER (MERRA-2 / CERES / GPM IMERG based, ~0.5°, public, no key) has
its daily values ~3 days late; MODIS MOD13Q1 NDVI (250 m) ~3-4 weeks late,
from the slow ORNL DAAC service (one request per ~9 composites).
Results are cached in memory per place and day.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fieldshift.api.providers.base import get_json

POWER_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_CLIMATE = "https://power.larc.nasa.gov/api/temporal/climatology/point"
MODIS_SUBSET = "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset"
# POWER parameters read for Status and Trends
DAILY_PARAMS = ("T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN",
                "WS2M", "GWETTOP", "TS")
CLIMATE_PARAMS = ("PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN")
# POWER climatology month keys
MONTH_KEYS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
              "DEC")
# days of one MODIS request (the service gives at most 10 composites)
MODIS_CHUNK_DAYS = 144

_cache = {}
_lock = threading.Lock()


def _cached(key, make):
    with _lock:
        if key in _cache:
            return _cache[key]
    value = make()
    with _lock:
        _cache[key] = value
    return value


# ()
# forgets every downloaded series
def clear_cache():
    with _lock:
        _cache.clear()


# (float lon, float lat, date start, date end)
# NASA POWER daily values: {parameter: [(iso date, value)]}, oldest first,
# missing days (fill values) left out
def power_daily(lon, lat, start, end):
    def make():
        response = get_json(POWER_DAILY, timeout=90, params={
            "parameters": ",".join(DAILY_PARAMS), "community": "AG", "format": "JSON",
            "longitude": round(lon, 4), "latitude": round(lat, 4),
            "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}"})
        fill = response.get("header", {}).get("fill_value", -999.0)
        result = {}
        for name, values in response["properties"]["parameter"].items():
            result[name] = [(f"{k[:4]}-{k[4:6]}-{k[6:8]}", float(v)) for k, v in
                            sorted(values.items()) if v is not None and v != fill]
        return result
    return _cached(("daily", round(lon, 3), round(lat, 3), start, end), make)


# (float lon, float lat)
# NASA POWER long-term normals: {parameter: [12 monthly values]} (rain in
# mm/day)
def power_climatology(lon, lat):
    def make():
        response = get_json(POWER_CLIMATE, timeout=90, params={
            "parameters": ",".join(CLIMATE_PARAMS), "community": "AG", "format": "JSON",
            "longitude": round(lon, 4), "latitude": round(lat, 4)})
        params = response["properties"]["parameter"]
        return {p: [float(params[p][m]) for m in MONTH_KEYS] for p in CLIMATE_PARAMS
                if p in params}
    return _cached(("climate", round(lon, 2), round(lat, 2)), make)


# (float lon, float lat, date start, date end)
# MODIS NDVI composites of the pixel at the point: [(iso date, ndvi)],
# oldest first (cloudy / fill pixels left out)
def modis_ndvi(lon, lat, start, end):
    def chunk(first):
        last = min(end, first + timedelta(days=MODIS_CHUNK_DAYS - 1))
        response = get_json(MODIS_SUBSET, timeout=120, params={
            "latitude": round(lat, 5), "longitude": round(lon, 5),
            "band": "250m_16_days_NDVI", "startDate": f"A{first:%Y%j}",
            "endDate": f"A{last:%Y%j}", "kmAboveBelow": 0, "kmLeftRight": 0})
        scale = float(response.get("scale") or 0.0001)
        out = []
        for item in response.get("subset", []):
            values = [v for v in item.get("data", []) if -2000 <= v <= 10000]
            if values:
                out.append((item["calendar_date"], sum(values) / len(values) * scale))
        return out

    def make():
        starts = []
        first = start
        while first <= end:
            starts.append(first)
            first += timedelta(days=MODIS_CHUNK_DAYS)
        with ThreadPoolExecutor(max_workers=len(starts)) as pool:
            parts = list(pool.map(chunk, starts))
        return sorted({d: v for part in parts for d, v in part}.items())
    return _cached(("ndvi", round(lon, 4), round(lat, 4), start, end), make)


# (float tmean, float radiation)
# reference evapotranspiration of a day, mm (Hargreaves radiation formula,
# radiation in MJ/m²/day)
def et0(tmean, radiation):
    return max(0.0, 0.0135 * (tmean + 17.8) * radiation * 0.408)


# ()
# today's date (a function so tests can replace it)
def today():
    return date.today()
