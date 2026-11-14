"""ECMWF ERA5-Land reanalysis: weather, soil moisture and soil temperature.

Copernicus Climate Data Store (CDS) with cdsapi; needs a free CDS account and
API key in ~/.cdsapirc (or CDSAPI_URL / CDSAPI_KEY). Hourly, 0.1° (~9 km),
published with ~5 days of delay. CDS requests are queued and can take several
minutes; downloads are cached in ~/.cache/fieldshift/era5_land.
"""

import hashlib
import json
import math
import os
from pathlib import Path

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import (
    NoData, Provider, ProviderUnavailable, cache_dir, circle_mask,
)

DATASET = "reanalysis-era5-land"
VARIABLES = [
    "2m_temperature", "2m_dewpoint_temperature", "total_precipitation",
    "surface_solar_radiation_downwards",
    "volumetric_soil_water_layer_1", "volumetric_soil_water_layer_2",
    "volumetric_soil_water_layer_3", "volumetric_soil_water_layer_4",
    "soil_temperature_level_1", "soil_temperature_level_2",
    "soil_temperature_level_3", "soil_temperature_level_4",
]
# ERA5-Land soil layers: index -> depth label
LAYERS = {1: "0-7cm", 2: "7-28cm", 3: "28-100cm", 4: "100-289cm"}
# grid spacing in degrees; the request box is at least this wide
GRID_DEG = 0.1


# (float t_c, float td_c)
# relative humidity in % from air and dewpoint temperature in °C (Magnus)
def relative_humidity(t_c, td_c):
    a, b = 17.625, 243.04
    return 100.0 * math.exp(a * td_c / (b + td_c) - a * t_c / (b + t_c))


# ERA5-Land provider: fills site.weather and soil moisture / temperature
class Era5LandProvider(Provider):
    name = "era5_land"
    title = "ECMWF ERA5-Land (hourly, 9 km) via CDS"
    url = "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land"
    packages = ("cdsapi", "xarray", "netCDF4", "numpy")
    credentials = "~/.cdsapirc or CDSAPI_URL + CDSAPI_KEY"

    def check(self):
        super().check()
        if not (os.environ.get("CDSAPI_KEY") or (Path.home() / ".cdsapirc").exists()):
            raise ProviderUnavailable("no CDS API key: create ~/.cdsapirc "
                                      "(see docs/data-api.md)")

    def fetch(self, area, period, site):
        import numpy as np
        import xarray as xr

        path = self._download(area, period)
        ds = xr.open_dataset(path)
        time_dim = "valid_time" if "valid_time" in ds.dims else "time"
        lat_name = "latitude" if "latitude" in ds.coords else "lat"
        lon_name = "longitude" if "longitude" in ds.coords else "lon"
        lons, lats = np.meshgrid(ds[lon_name].values, ds[lat_name].values)
        mask = xr.DataArray(circle_mask(lons, lats, area), dims=(lat_name, lon_name))

        def series(var):
            da = ds[var].where(mask).mean(dim=(lat_name, lon_name), skipna=True)
            start = np.datetime64(period.start, "ns")
            end = np.datetime64(period.end, "ns") + np.timedelta64(1, "D")
            # accumulations: the value at 00 UTC closes the previous day
            shift = np.timedelta64(1, "h") if var in ("tp", "ssrd") else np.timedelta64(0, "h")
            t = da[time_dim].values - shift
            keep = (t >= start) & (t < end)
            return da.isel({time_dim: keep}), t[keep]

        if "t2m" not in ds:
            raise NoData("ERA5-Land returned no data")
        w, src = site.weather, self.name
        t2m, _ = series("t2m")
        if t2m.size == 0 or np.isnan(t2m).all():
            raise NoData("no ERA5-Land land cells here (sea?)")
        t_c = t2m - 273.15
        w.air_temperature = Measurement(float(t_c.mean()), "°C", src)
        w.air_temperature_min = Measurement(float(t_c.min()), "°C", src)
        w.air_temperature_max = Measurement(float(t_c.max()), "°C", src)
        d2m, _ = series("d2m")
        td_c = float((d2m - 273.15).mean())
        w.dewpoint = Measurement(td_c, "°C", src)
        w.relative_humidity = Measurement(relative_humidity(float(t_c.mean()), td_c), "%", src,
                                          "from mean temperature and dewpoint")
        for var, attr, factor, unit in (("tp", "precipitation", 1000.0, "mm"),
                                        ("ssrd", "solar_radiation", 1e-6, "MJ/m²/day")):
            da, t = series(var)
            day = xr.DataArray(t.astype("datetime64[D]"), dims=time_dim, name="day")
            daily = da.groupby(day).max()
            if attr == "precipitation":
                setattr(w, attr, Measurement(float(daily.sum()) * factor, unit, src,
                                             "total over the period"))
            else:
                setattr(w, attr, Measurement(float(daily.mean()) * factor, unit, src,
                                             "mean daily irradiation"))
        for i, depth in LAYERS.items():
            sm, _ = series(f"swvl{i}")
            st, _ = series(f"stl{i}")
            site.soil.moisture[f"{depth} ERA5-Land"] = Measurement(
                float(sm.mean()) * 100, "% vol", src)
            site.soil.temperature[f"{depth} ERA5-Land"] = Measurement(
                float(st.mean()) - 273.15, "°C", src)

    # (Area area, Period period)
    # downloads (or reuses from cache) the NetCDF for the area and period
    def _download(self, area, period):
        import cdsapi
        from datetime import timedelta
        west, south, east, north = area.bbox(min_deg=GRID_DEG)
        # one extra day so the last day's accumulations (00 UTC next day) exist
        days = period.days() + [period.end + timedelta(days=1)]
        request = {
            "variable": VARIABLES,
            "year": sorted({f"{d:%Y}" for d in days}),
            "month": sorted({f"{d:%m}" for d in days}),
            "day": sorted({f"{d:%d}" for d in days}),
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [round(north, 2), round(west, 2), round(south, 2), round(east, 2)],
            "data_format": "netcdf",
            "download_format": "unarchived",
        }
        key = hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()[:16]
        path = cache_dir(self.name) / f"{key}.nc"
        if not path.exists():
            tmp = path.with_suffix(".part")
            cdsapi.Client(quiet=True).retrieve(DATASET, request, str(tmp))
            tmp.rename(path)
        return path
