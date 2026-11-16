"""Data the real analyses read, in one place (cached, replaceable in tests).

    power_daily(lon, lat, start, end)   NASA POWER daily point data
    power_climatology(lon, lat)         NASA POWER monthly normals
    wapor_grids(mapset, field, months)  FAO WaPOR monthly rasters sampled on
                                        a GRID x GRID grid over the field
    dem_grid(field)                     Copernicus DEM on the same grid
    forecast(lon, lat)                  Open-Meteo 7-day forecast
    crop_requirements(field)            FAO EcoCrop data of the field's crop

Grids are rows north to south over the field's bounding box, like
analysis.models.MapFrames; a cell without data is None.
"""

import datetime as dt
import hashlib
import json
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fieldshift.api.providers.base import get_json

# cells per side of the map grids
GRID = 8
# months covered by the time series
MONTHS = 24
POWER_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_CLIMATOLOGY = "https://power.larc.nasa.gov/api/temporal/climatology/point"
WAPOR_COG = ("https://storage.googleapis.com/fao-gismgr-wapor-3-data/DATA/WAPOR-3/MAPSET/"
             "{mapset}/WAPOR-3.{mapset}.{month}.tif")
# today's date used by the analyses (tests set it)
TODAY = None

_cache = {}
_lock = threading.Lock()


def today():
    return TODAY or dt.date.today()


# (int n = MONTHS)
# the last n complete months, oldest first: ["2024-11", ..., "2026-10"]
def last_months(n=MONTHS):
    year, month = today().year, today().month
    out = []
    for _ in range(n):
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        out.append(f"{year}-{month:02d}")
    return out[::-1]


# (Field field)
# (lon, lat) of the field's centre
def center(field):
    return (sum(v[0] for v in field.vertices) / len(field.vertices),
            sum(v[1] for v in field.vertices) / len(field.vertices))


# (Field field)
# (lon, lat) of the centres of the GRID x GRID cells, rows north to south
def grid_points(field):
    lons = [v[0] for v in field.vertices]
    lats = [v[1] for v in field.vertices]
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)
    return [[(west + (c + 0.5) * (east - west) / GRID, north - (r + 0.5) * (north - south) / GRID)
             for c in range(GRID)] for r in range(GRID)]


def _cached(key, compute):
    with _lock:
        if key in _cache:
            return _cache[key]
    value = compute()
    with _lock:
        _cache[key] = value
    return value


# ()
# forgets everything downloaded (tests, or to force new downloads)
def clear_cache():
    with _lock:
        _cache.clear()


# (float lon, float lat, dt.date start, dt.date end)
# {"T2M_MIN" | "T2M_MAX" | "PRECTOTCORR" | "GWETROOT": {date: value}}
# (fill values dropped). Raises on failure
def power_daily(lon, lat, start, end):
    def compute():
        response = get_json(POWER_DAILY, timeout=90, params={
            "parameters": "T2M_MIN,T2M_MAX,PRECTOTCORR,GWETROOT", "community": "AG",
            "format": "JSON", "longitude": round(lon, 3), "latitude": round(lat, 3),
            "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}"})
        fill = response.get("header", {}).get("fill_value", -999.0)
        out = {}
        for name, values in response["properties"]["parameter"].items():
            out[name] = {dt.datetime.strptime(k, "%Y%m%d").date(): float(v)
                         for k, v in values.items() if v is not None and v != fill}
        return out
    return _cached(("power_daily", round(lon, 3), round(lat, 3), start, end), compute)


# (float lon, float lat)
# {"T2M" | "T2M_MIN" | "T2M_MAX" | "PRECTOTCORR" | "FROST_DAYS": {"JAN".. "ANN": value}}
def power_climatology(lon, lat):
    def compute():
        response = get_json(POWER_CLIMATOLOGY, timeout=90, params={
            "parameters": "T2M,T2M_MIN,T2M_MAX,PRECTOTCORR,FROST_DAYS", "community": "AG",
            "format": "JSON", "longitude": round(lon, 3), "latitude": round(lat, 3)})
        return response["properties"]["parameter"]
    return _cached(("power_clim", round(lon, 3), round(lat, 3)), compute)


# (str mapset, Field field, list months)
# {month: GRID x GRID physical values or None} of a WaPOR monthly mapset
# ("L1-NPP-M", "L1-AETI-M"...), months read in parallel
def wapor_grids(mapset, field, months):
    points = grid_points(field)

    def one(month):
        key = ("wapor", mapset, month, tuple(field.vertices))
        return month, _cached(key, lambda: _disk_cached(key, lambda: _sample_cog(
            WAPOR_COG.format(mapset=mapset, month=month), points)))
    # each month is a global file whose header alone takes seconds to read:
    # a few at a time (many at once made the app stutter), kept on disk after
    with ThreadPoolExecutor(max_workers=WAPOR_WORKERS) as pool:
        return dict(pool.map(one, months))


# WaPOR files read at the same time
WAPOR_WORKERS = 6


# ()
# folder of the downloaded values kept between runs (published WaPOR months
# never change): FIELDSHIFT_CACHE_DIR, else ~/.cache/fieldshift. None when
# the app runs offline (tests)
def disk_cache_dir():
    if os.environ.get("FIELDSHIFT_OFFLINE") == "1":
        return None
    folder = os.environ.get("FIELDSHIFT_CACHE_DIR")
    return Path(folder) if folder else Path.home() / ".cache" / "fieldshift"


# (tuple key, callable compute)
# compute() kept in a small JSON file per key; None results are not kept
# (the month may be published later)
def _disk_cached(key, compute):
    folder = disk_cache_dir()
    if folder is None:
        return compute()
    name = hashlib.sha1(repr(key).encode()).hexdigest()
    path = folder / "wapor" / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    value = compute()
    if value is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding="utf-8")
        except OSError:
            pass                                   # no cache: still works
    return value


def _sample_cog(url, points):
    import numpy as np
    import rasterio
    from rasterio.errors import RasterioIOError
    from rasterio.windows import from_bounds
    flat = [p for row in points for p in row]
    lons, lats = [p[0] for p in flat], [p[1] for p in flat]
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open("/vsicurl/" + url) as src:
                res = abs(src.transform.a)
                window = from_bounds(min(lons) - res, min(lats) - res, max(lons) + res,
                                     max(lats) + res, src.transform)
                window = window.round_offsets().round_lengths()
                data = src.read(1, window=window, masked=True, boundless=True)
                transform = src.window_transform(window)
                scale, offset = (src.scales or (1.0,))[0], (src.offsets or (0.0,))[0]
    except RasterioIOError:
        return None                                # month not published
    grid = []
    for row in points:
        cells = []
        for lon, lat in row:
            c, r = ~transform * (lon, lat)
            r, c = int(math.floor(r)), int(math.floor(c))
            if 0 <= r < data.shape[0] and 0 <= c < data.shape[1] and not np.ma.is_masked(data[r, c]):
                cells.append(float(data[r, c]) * scale + offset)
            else:
                cells.append(None)
        grid.append(cells)
    return grid if any(v is not None for row in grid for v in row) else None


# (Field field)
# GRID x GRID elevations (m) from the Copernicus DEM, or None when unavailable
def dem_grid(field):
    def compute():
        from fieldshift.api.providers.copernicus_dem import tiles_for
        points = grid_points(field)
        flat = [p for row in points for p in row]
        bbox = (min(p[0] for p in flat), min(p[1] for p in flat),
                max(p[0] for p in flat), max(p[1] for p in flat))
        merged = None
        for url in tiles_for(bbox):                 # a field may cross tile edges
            grid = _sample_cog(url, points)
            if grid is None:
                continue
            if merged is None:
                merged = grid
            else:
                merged = [[a if a is not None else b for a, b in zip(ra, rb)]
                          for ra, rb in zip(merged, grid)]
        return merged
    return _cached(("dem", tuple(field.vertices)), compute)


# (float lon, float lat)
# fieldshift.api.forecast.Forecast; raises when the service fails
def forecast(lon, lat):
    from fieldshift.api.forecast import get_forecast
    return get_forecast(lon, lat)


# (Field field)
# ecocrop.CropInfo of the field's crop, or None (no crop, no EcoCrop data)
def crop_requirements(field):
    from fieldshift import crops
    value = ((field.data or {}).get("crop") or {}).get("value")
    if not value:
        return None
    target = crops.ecocrop_number(value) or crops.ecocrop_name(value)
    return crop_requirements_of(target) if target else None


# (int|str target)
# ecocrop.CropInfo of an EcoCrop id or scientific name, or None on failure
def crop_requirements_of(target):
    from fieldshift.crops import ecocrop
    try:
        return ecocrop.get_crop(target)
    except Exception:
        return None
