"""NASA GPM IMERG V07 daily (late run): satellite precipitation.

Needs a free NASA Earthdata account (earthaccess). 0.1° grid, one global
NetCDF granule per day; only the cells around the area are read.
"""

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, circle_mask, earthdata_login

SHORT_NAME = "GPM_3IMERGDL"
# at most this many days are read (one granule per day)
MAX_DAYS = 31


# GPM IMERG provider: fills site.water.precipitation_satellite
class GpmImergProvider(Provider):
    name = "gpm_imerg"
    title = "NASA GPM IMERG V07 daily late run (0.1°)"
    url = "https://gpm.nasa.gov/data/imerg"
    packages = ("earthaccess", "xarray", "h5netcdf", "numpy")
    credentials = "NASA Earthdata (EARTHDATA_USERNAME/PASSWORD or ~/.netrc)"

    def check(self):
        super().check()
        earthdata_login()

    def fetch(self, area, period, site):
        import earthaccess
        import numpy as np
        import xarray as xr

        granules = earthaccess.search_data(
            short_name=SHORT_NAME, version="07", bounding_box=area.bbox(min_deg=0.1),
            temporal=(f"{period.start}", f"{period.end}T23:59:59"))[:MAX_DAYS]
        if not granules:
            raise NoData("no IMERG granules for the period (not published yet?)")
        west, south, east, north = area.bbox(min_deg=0.1)
        daily = []
        for fobj in earthaccess.open(granules):
            ds = xr.open_dataset(fobj, engine="h5netcdf")
            pr = ds["precipitation"].isel(time=0).sel(
                lon=slice(west, east), lat=slice(south, north)).transpose("lon", "lat")
            lons, lats = np.meshgrid(pr["lon"].values, pr["lat"].values, indexing="ij")
            vals = pr.values[circle_mask(lons, lats, area)]
            vals = vals[np.isfinite(vals) & (vals >= 0)]
            if vals.size:
                daily.append(float(vals.mean()))
        if not daily:
            raise NoData("IMERG has no valid cells here")
        site.water.precipitation_satellite = Measurement(
            sum(daily), "mm", self.name, f"total of {len(daily)} day(s)")
