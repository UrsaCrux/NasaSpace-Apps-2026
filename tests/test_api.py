"""Tests for fieldshift.api.

Offline by default: providers are fed synthetic files / responses in the
format of each product. Set FIELDSHIFT_LIVE=1 to also query the public
sources that need no key (SoilGrids, Copernicus DEM, WaPOR).
"""

import importlib.util
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from fieldshift.api import Area, Period, SiteData, get_site_data, list_providers
from fieldshift.api.models import Measurement
from fieldshift.api.providers import NoData, Provider, ProviderUnavailable
from fieldshift.api.providers import (
    copernicus_dem, era5_land, firms, grace, modis_ndvi, nasa_power, soilgrids, wapor,
)

LIVE = os.environ.get("FIELDSHIFT_LIVE") == "1"
# farmland in O'Higgins, Chile (Santiago itself is masked by SoilGrids)
LON, LAT = -71.0, -34.5


def has(*modules):
    return all(importlib.util.find_spec(m) is not None for m in modules)


class GeoTest(unittest.TestCase):
    def test_bbox_and_contains(self):
        a = Area(LON, LAT, 1000)
        w, s, e, n = a.bbox()
        self.assertAlmostEqual(n - LAT, 1000 / 111_320, places=6)
        self.assertGreater(e - LON, n - LAT)            # degrees of lon are shorter
        self.assertTrue(a.contains(LON + 0.005, LAT))
        self.assertFalse(a.contains(LON + 0.02, LAT))
        self.assertAlmostEqual(Area(LON, LAT, 0).bbox(min_deg=0.1)[2] - LON, 0.1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            Area(200, 0)
        with self.assertRaises(ValueError):
            Period(date(2026, 1, 2), date(2026, 1, 1))

    def test_period(self):
        p = Period.make("2026-10-30", "2026-11-02")
        self.assertEqual(len(p), 4)
        self.assertEqual(p.days()[-1], date(2026, 11, 2))
        self.assertEqual(len(Period.make()), 7)


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, behaviour):
        self.behaviour = behaviour

    def fetch(self, area, period, site):
        if self.behaviour == "ok":
            site.terrain.elevation = Measurement(10, "m", self.name)
        elif self.behaviour == "skip":
            raise ProviderUnavailable("no key")
        elif self.behaviour == "nodata":
            raise NoData("sea")
        else:
            raise RuntimeError("boom")


class ClientTest(unittest.TestCase):
    def test_errors_are_reported_not_raised(self):
        classes = [type(f"P{b}", (FakeProvider,), {"name": b,
                   "__init__": lambda self, b=b: FakeProvider.__init__(self, b)})
                   for b in ("ok", "skip", "nodata", "boom")]
        with mock.patch("fieldshift.api.client.PROVIDERS", classes):
            site = get_site_data(LON, LAT, 500)
        status = {s.name: s.status for s in site.sources}
        self.assertEqual(status["ok"], "ok")
        self.assertEqual(status["skip"], "skipped")
        self.assertEqual(status["nodata"], "no_data")
        self.assertEqual(status["boom"], "error")
        self.assertIn("planned", status.values())
        self.assertEqual(site.terrain.elevation.value, 10)
        self.assertIn("elevation", site.summary())
        self.assertEqual(site.to_dict()["period"]["end"], site.period.end.isoformat())

    def test_list_providers(self):
        names = [n for n, _, _ in list_providers()]
        self.assertIn("soilgrids", names)
        self.assertIn("inia", names)


class SoilGridsParseTest(unittest.TestCase):
    def test_parse(self):
        response = {"properties": {"layers": [
            {"name": "clay", "unit_measure": {"d_factor": 10},
             "depths": [{"label": "0-5cm", "values": {"mean": 211}},
                        {"label": "5-15cm", "values": {"mean": None}}]},
            {"name": "wv0033", "unit_measure": {"d_factor": 10},
             "depths": [{"label": "0-5cm", "values": {"mean": 304}}]}]}}
        site = SiteData(Area(LON, LAT), Period.make())
        self.assertEqual(soilgrids.parse_properties(response, site.soil, "sg"), 2)
        self.assertAlmostEqual(site.soil.clay["0-5cm"].value, 21.1)
        self.assertAlmostEqual(site.soil.field_capacity["0-5cm"].value, 30.4)
        self.assertNotIn("5-15cm", site.soil.clay)


class NamingTest(unittest.TestCase):
    def test_dem_tiles(self):
        self.assertTrue(copernicus_dem.tile_url(-35, -72).endswith(
            "Copernicus_DSM_COG_10_S35_00_W072_00_DEM.tif"))
        self.assertTrue(copernicus_dem.tile_url(40, 5).endswith("N40_00_E005_00_DEM.tif"))
        self.assertEqual(len(copernicus_dem.tiles_for((-71.01, -34.51, -70.99, -34.49))), 2)

    def test_wapor_dekads(self):
        self.assertEqual(wapor.dekad_codes(Period.make("2026-10-30", "2026-11-12")),
                         ["2026-10-D3", "2026-11-D1", "2026-11-D2"])

    def test_relative_humidity(self):
        self.assertAlmostEqual(era5_land.relative_humidity(20, 20), 100)
        self.assertAlmostEqual(era5_land.relative_humidity(20, 10), 52.6, delta=1)


@unittest.skipUnless(has("xarray", "netCDF4", "numpy", "cdsapi"), "xarray/netCDF4/cdsapi missing")
class Era5ProcessingTest(unittest.TestCase):
    """Feeds a synthetic file in the CDS ERA5-Land NetCDF layout."""

    def test_fetch(self):
        import numpy as np
        import pandas as pd
        import xarray as xr

        period = Period.make("2026-11-01", "2026-11-02")
        times = pd.date_range("2026-11-01T00", "2026-11-03T23", freq="h")
        lat = np.array([-34.4, -34.5, -34.6])
        lon = np.array([-71.1, -71.0, -70.9])
        shape = (len(times), 3, 3)
        hours = np.asarray(times.hour)
        # accumulation since 00 UTC: 1 mm per hour, value at 00 UTC = 24 h total
        acc = np.where(hours == 0, 24, hours)[:, None, None] * np.ones(shape)
        ds = xr.Dataset(
            {"t2m": (("valid_time", "latitude", "longitude"), np.full(shape, 293.15)),
             "d2m": (("valid_time", "latitude", "longitude"), np.full(shape, 283.15)),
             "tp": (("valid_time", "latitude", "longitude"), acc * 0.001),
             "ssrd": (("valid_time", "latitude", "longitude"), acc * 1e6)},
            coords={"valid_time": times, "latitude": lat, "longitude": lon})
        for i in range(1, 5):
            ds[f"swvl{i}"] = (("valid_time", "latitude", "longitude"), np.full(shape, 0.25))
            ds[f"stl{i}"] = (("valid_time", "latitude", "longitude"), np.full(shape, 288.15))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "era5.nc"
            ds.to_netcdf(path)
            site = SiteData(Area(LON, LAT, 1000), period)
            provider = era5_land.Era5LandProvider()
            with mock.patch.object(provider, "_download", return_value=path):
                provider.fetch(site.area, period, site)
        w = site.weather_by_source["era5_land"]
        self.assertAlmostEqual(w.air_temperature.value, 20.0)
        self.assertEqual(w.frost_days.value, 0)
        self.assertEqual(w.heat_days.value, 0)
        self.assertAlmostEqual(w.max_daily_precipitation.value, 24.0)
        self.assertAlmostEqual(w.dewpoint.value, 10.0)
        self.assertAlmostEqual(w.precipitation.value, 48.0)     # 2 days x 24 mm
        self.assertAlmostEqual(w.solar_radiation.value, 24.0)   # MJ/m²/day
        self.assertAlmostEqual(site.soil.moisture["0-7cm ERA5-Land"].value, 25.0)
        self.assertAlmostEqual(site.soil.temperature["100-289cm ERA5-Land"].value, 15.0)


@unittest.skipUnless(has("earthaccess", "h5py", "numpy"), "earthaccess/h5py missing")
class SmapProcessingTest(unittest.TestCase):
    """Feeds a synthetic granule in the SPL4SMGP HDF5 layout."""

    def test_fetch(self):
        import h5py
        import numpy as np
        from fieldshift.api.providers import smap

        lats = np.linspace(-34.0, -35.0, 12)
        lons = np.linspace(-71.5, -70.5, 12)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smap.h5"
            with h5py.File(path, "w") as f:
                f["cell_lat"] = np.repeat(lats[:, None], 12, axis=1)
                f["cell_lon"] = np.repeat(lons[None, :], 12, axis=0)
                g = f.create_group("Geophysical_Data")
                g["sm_surface"] = np.full((12, 12), 0.3, dtype="f4")
                g["sm_rootzone"] = np.full((12, 12), 0.2, dtype="f4")
                g["soil_temp_layer1"] = np.full((12, 12), 290.15, dtype="f4")
                g["surface_temp"] = np.full((12, 12), -9999.0, dtype="f4")
            site = SiteData(Area(LON, LAT, 1000), Period.make())
            with mock.patch("earthaccess.search_data", return_value=["g1"]), \
                    mock.patch("earthaccess.open", return_value=[str(path)]):
                smap.SmapProvider().fetch(site.area, site.period, site)
        self.assertAlmostEqual(site.soil.moisture["0-5cm SMAP"].value, 30.0, places=4)
        self.assertAlmostEqual(site.soil.moisture["0-100cm SMAP"].value, 20.0, places=4)
        self.assertAlmostEqual(site.soil.temperature["0-10cm SMAP"].value, 17.0, places=3)
        self.assertNotIn("surface SMAP", site.soil.temperature)     # only fill values


@unittest.skipUnless(has("earthaccess", "xarray", "h5netcdf", "numpy"), "earthaccess missing")
class ImergProcessingTest(unittest.TestCase):
    """Feeds synthetic daily granules in the IMERG V07 NetCDF layout."""

    def test_fetch(self):
        import numpy as np
        import pandas as pd
        import xarray as xr
        from fieldshift.api.providers import gpm_imerg

        lon = np.round(np.arange(-71.45, -70.5, 0.1), 2)
        lat = np.round(np.arange(-34.95, -34.0, 0.1), 2)
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i, mm in enumerate((2.0, 5.0)):
                ds = xr.Dataset({"precipitation": (("time", "lon", "lat"),
                                                   np.full((1, lon.size, lat.size), mm))},
                                coords={"time": pd.date_range(f"2026-11-0{i + 1}", periods=1),
                                        "lon": lon, "lat": lat})
                paths.append(str(Path(tmp) / f"d{i}.nc"))
                ds.to_netcdf(paths[-1], engine="h5netcdf")
            site = SiteData(Area(LON, LAT, 3000), Period.make("2026-11-01", "2026-11-02"))
            with mock.patch("earthaccess.search_data", return_value=["a", "b"]), \
                    mock.patch("earthaccess.open", return_value=paths):
                gpm_imerg.GpmImergProvider().fetch(site.area, site.period, site)
        self.assertAlmostEqual(site.water.precipitation_satellite.value, 7.0)


class FirmsParseTest(unittest.TestCase):
    def test_fetch(self):
        csv_text = ("latitude,longitude,acq_date,frp,confidence\n"
                    f"{LAT},{LON + 0.005},2026-11-05,12.5,h\n"
                    f"{LAT + 0.5},{LON},2026-11-05,3.0,n\n")
        site = SiteData(Area(LON, LAT, 1000), Period.make())
        with mock.patch.dict(os.environ, {"FIRMS_MAP_KEY": "x"}), \
                mock.patch.object(firms, "get_text", return_value=csv_text):
            firms.FirmsProvider().fetch(site.area, site.period, site)
        self.assertEqual(site.fires.count, 1)
        self.assertAlmostEqual(site.fires.nearest_km, 0.46, delta=0.05)


class WeatherMergeTest(unittest.TestCase):
    def test_priority_then_fill(self):
        from fieldshift.api.models import Weather
        site = SiteData(Area(LON, LAT), Period.make())
        site.weather_by_source["nasa_power"] = Weather(
            air_temperature=Measurement(15, "°C", "nasa_power"),
            wind_speed=Measurement(2, "m/s", "nasa_power"))
        site.weather_by_source["era5_land"] = Weather(
            air_temperature=Measurement(14, "°C", "era5_land"))
        site.merge_weather(["era5_land", "nasa_power"])
        self.assertEqual(site.weather.air_temperature.source, "era5_land")
        self.assertEqual(site.weather.wind_speed.source, "nasa_power")


class NasaPowerParseTest(unittest.TestCase):
    def test_daily_and_climate(self):
        daily = {"header": {"fill_value": -999.0}, "properties": {"parameter": {
            "T2M": {"20261101": 10.0, "20261102": 14.0},
            "T2M_MIN": {"20261101": -1.0, "20261102": 3.0},
            "T2M_MAX": {"20261101": 36.0, "20261102": 20.0},
            "PRECTOTCORR": {"20261101": 4.0, "20261102": -999.0},
            "GWETTOP": {"20261101": 0.5, "20261102": 0.7}}}}
        clim = {"messages": ["... pre-computed climatological period (January 2001 - "
                             "December 2025)"],
                "header": {"fill_value": -999.0},
                "properties": {"parameter": {"T2M": {"JAN": 22.4, "ANN": 15.9},
                                             "FROST_DAYS": {"JAN": 0.0, "ANN": 0.8}}}}
        site = SiteData(Area(LON, LAT), Period.make("2026-11-01", "2026-11-02"))
        with mock.patch.object(nasa_power, "get_json", side_effect=[daily, clim]):
            nasa_power.NasaPowerProvider().fetch(site.area, site.period, site)
        w = site.weather_by_source["nasa_power"]
        self.assertAlmostEqual(w.air_temperature.value, 12.0)
        self.assertEqual(w.frost_days.value, 1)
        self.assertEqual(w.heat_days.value, 1)
        self.assertAlmostEqual(w.precipitation.value, 4.0)          # fill value dropped
        self.assertAlmostEqual(site.soil.moisture["0-5cm POWER wetness"].value, 60.0)
        self.assertEqual(site.climate.years, "January 2001 - December 2025")
        self.assertAlmostEqual(site.climate.frost_days["ANN"].value, 0.8)
        self.assertIn("Climate normals", site.summary())


class ModisNdviParseTest(unittest.TestCase):
    def test_parse_subset(self):
        # 3x3 MODIS cells centred on the point, in sinusoidal metres
        import math
        cell = 231.656358264
        y = math.radians(LAT) * modis_ndvi.SIN_R
        x = math.radians(LON) * modis_ndvi.SIN_R * math.cos(math.radians(LAT))
        response = {"nrows": 3, "ncols": 3, "cellsize": cell, "scale": "0.0001",
                    "xllcorner": x - 1.5 * cell, "yllcorner": y - 1.5 * cell,
                    "subset": [{"calendar_date": "2026-10-16",
                                "data": [5000, 5000, 5000, 5000, 7000, 5000, 5000, 5000, -3000]}]}
        (date_, vals), = modis_ndvi.parse_subset(response, Area(LON, LAT, 100))
        self.assertEqual(date_, "2026-10-16")
        self.assertEqual(len(vals), 1)                  # only the centre cell is inside
        self.assertAlmostEqual(vals[0], 0.7)
        (_, vals), = modis_ndvi.parse_subset(response, Area(LON, LAT, 1000))
        self.assertEqual(len(vals), 8)                  # fill value -3000 dropped


@unittest.skipUnless(has("requests", "numpy"), "requests missing")
class ModisRetryTest(unittest.TestCase):
    def test_retry_with_centre_pixel_on_502(self):
        import requests
        error = requests.HTTPError(response=mock.Mock(status_code=502))
        ok = {"nrows": 1, "ncols": 1, "cellsize": 231.6, "scale": "0.0001",
              "xllcorner": -6506532.17, "yllcorner": -3836460.91,
              "subset": [{"calendar_date": "2026-10-16", "data": [6000]}]}
        site = SiteData(Area(LON, LAT, 1500), Period.make("2026-11-01", "2026-11-07"))
        with mock.patch.object(modis_ndvi, "get_json", side_effect=[error, ok]) as get:
            modis_ndvi.ModisNdviProvider().fetch(site.area, site.period, site)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["kmAboveBelow"], 0)
        self.assertAlmostEqual(site.vegetation.ndvi.value, 0.6)
        self.assertIn("centre pixel only", site.vegetation.ndvi.note)


@unittest.skipUnless(has("numpy"), "numpy missing")
class GraceTrendTest(unittest.TestCase):
    def test_trend(self):
        import numpy as np
        times = np.arange("2016-01", "2026-01", dtype="datetime64[M]").astype("datetime64[D]")
        values = -2.0 * np.arange(times.size) / 12.0          # -2 cm per year
        self.assertAlmostEqual(grace.trend_cm_per_year(times, values), -2.0, delta=0.02)


@unittest.skipUnless(has("earthaccess", "xarray", "h5netcdf", "numpy"), "earthaccess missing")
class GraceProcessingTest(unittest.TestCase):
    """Feeds a synthetic file in the JPL mascon NetCDF layout (0..360 lon)."""

    def test_fetch(self):
        import numpy as np
        import xarray as xr
        times = np.arange("2016-01", "2026-10", dtype="datetime64[M]").astype("datetime64[ns]")
        lat = np.arange(-35.75, -33.0, 0.5)
        lon = np.arange(288.25, 290.0, 0.5)
        series = -1.5 * np.arange(times.size) / 12.0
        ds = xr.Dataset({"lwe_thickness": (("time", "lat", "lon"),
                                           series[:, None, None] * np.ones((1, lat.size, lon.size)))},
                        coords={"time": times, "lat": lat, "lon": lon})
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "grace.nc")
            ds.to_netcdf(path, engine="h5netcdf")
            site = SiteData(Area(LON, LAT, 1000), Period.make("2026-11-01", "2026-11-07"))
            with mock.patch("earthaccess.search_data", return_value=["g"]), \
                    mock.patch("earthaccess.open", return_value=[path]):
                grace.GraceProvider().fetch(site.area, site.period, site)
        self.assertAlmostEqual(site.water.storage_trend.value, -1.5, delta=0.02)
        self.assertIn("2026-09", site.water.storage_anomaly.note)


@unittest.skipUnless(has("earthaccess", "xarray", "h5netcdf", "numpy"), "earthaccess missing")
class GldasProcessingTest(unittest.TestCase):
    """Feeds a synthetic monthly granule in the GLDAS Noah 2.1 layout."""

    def test_fetch(self):
        import numpy as np
        import pandas as pd
        import xarray as xr
        from fieldshift.api.providers import gldas
        lat = np.arange(-35.125, -33.9, 0.25)
        lon = np.arange(-71.625, -70.4, 0.25)
        shape = (1, lat.size, lon.size)
        ds = xr.Dataset({
            "SoilMoi0_10cm_inst": (("time", "lat", "lon"), np.full(shape, 25.0)),   # kg/m²
            "SoilTMP0_10cm_inst": (("time", "lat", "lon"), np.full(shape, 288.15)),
            "Evap_tavg": (("time", "lat", "lon"), np.full(shape, 2.0 / 86400))},
            coords={"time": pd.date_range("2026-07-01", periods=1), "lat": lat, "lon": lon})
        granule = {"umm": {"TemporalExtent": {"RangeDateTime": {
            "BeginningDateTime": "2026-07-01T00:00:00.000Z"}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "gldas.nc4")
            ds.to_netcdf(path, engine="h5netcdf")
            site = SiteData(Area(LON, LAT, 1000), Period.make("2026-11-01", "2026-11-07"))
            with mock.patch("earthaccess.search_data", return_value=[granule]), \
                    mock.patch("earthaccess.open", return_value=[path]):
                gldas.GldasProvider().fetch(site.area, site.period, site)
        self.assertAlmostEqual(site.soil.moisture["0-10cm GLDAS"].value, 25.0)    # % vol
        self.assertAlmostEqual(site.soil.temperature["0-10cm GLDAS"].value, 15.0)
        self.assertAlmostEqual(site.water.actual_et_gldas.value, 2.0)
        self.assertIn("latest month 2026-07", site.water.actual_et_gldas.note)


@unittest.skipUnless(has("rasterio", "numpy"), "rasterio missing")
class EcostressReadTest(unittest.TestCase):
    """read_cog on a small UTM GeoTIFF like an ECOSTRESS tile, with a cloud mask."""

    def test_read_cog(self):
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.warp import transform
        from fieldshift.api.providers import ecostress
        (x,), (y,) = transform("EPSG:4326", "EPSG:32719", [LON], [LAT])
        tf = from_origin(x - 70 * 10, y + 70 * 10, 70, 70)        # 20x20 px of 70 m
        et = np.full((20, 20), 4.0, dtype="float32")
        et[10, 10] = np.nan
        cloud = np.zeros((20, 20), dtype="uint8")
        cloud[:, :10] = 1                                          # west half cloudy
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for name, arr in (("et", et), ("cloud", cloud)):
                paths[name] = str(Path(tmp) / f"{name}.tif")
                with rasterio.open(paths[name], "w", driver="GTiff", height=20, width=20,
                                   count=1, dtype=arr.dtype, crs="EPSG:32719", transform=tf,
                                   nodata=None) as dst:
                    dst.write(arr, 1)
            vals = ecostress.read_cog(paths["et"], Area(LON, LAT, 300))
            clear = ecostress.read_cog(paths["et"], Area(LON, LAT, 300),
                                       cloud_url=paths["cloud"])
        self.assertTrue(vals and all(v == 4.0 for v in vals))     # NaN pixel dropped
        self.assertLess(len(clear), len(vals))                     # cloudy pixels dropped


@unittest.skipUnless(LIVE, "set FIELDSHIFT_LIVE=1 to query the public APIs")
class LiveTest(unittest.TestCase):
    def test_public_sources(self):
        public = ["nasa_power", "soilgrids", "copernicus_dem", "wapor", "modis_ndvi"]
        site = get_site_data(LON, LAT, 1500, providers=public)
        status = {s.name: (s.status, s.message) for s in site.sources}
        for name in public:
            self.assertEqual(status[name][0], "ok", status[name])
        self.assertTrue(site.soil.type.value)
        self.assertGreater(site.terrain.elevation.value, 0)
        self.assertGreater(site.water.reference_et.value, 0)
        self.assertEqual(site.weather.air_temperature.source, "nasa_power")
        self.assertEqual(len(site.climate.frost_days), 13)
        self.assertTrue(-1 <= site.vegetation.ndvi.value <= 1)


if __name__ == "__main__":
    unittest.main()
