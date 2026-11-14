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
from fieldshift.api.providers import copernicus_dem, era5_land, firms, soilgrids, wapor

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
        w = site.weather
        self.assertAlmostEqual(w.air_temperature.value, 20.0)
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


@unittest.skipUnless(LIVE, "set FIELDSHIFT_LIVE=1 to query the public APIs")
class LiveTest(unittest.TestCase):
    def test_public_sources(self):
        site = get_site_data(LON, LAT, 1500,
                             providers=["soilgrids", "copernicus_dem", "wapor"])
        status = {s.name: (s.status, s.message) for s in site.sources}
        for name in ("soilgrids", "copernicus_dem", "wapor"):
            self.assertEqual(status[name][0], "ok", status[name])
        self.assertTrue(site.soil.type.value)
        self.assertGreater(site.terrain.elevation.value, 0)
        self.assertGreater(site.water.reference_et.value, 0)


if __name__ == "__main__":
    unittest.main()
