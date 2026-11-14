"""GRACE / GRACE-FO JPL mascons RL06.3 v4: terrestrial water storage.

Needs a free NASA Earthdata account (earthaccess). One global NetCDF with
every month since 2002 (0.5° grid, ~3° mascons); only the cells around the
area are read. Gives the latest monthly anomaly (relative to the 2004-2009
mean) and the linear trend over the last TREND_YEARS years: a long-term
signal of groundwater and soil-water gain or loss.
"""

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, earthdata_login

SHORT_NAME = "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4"
# years used for the trend
TREND_YEARS = 10
# mascons are ~3° wide: the box read around the area, in degrees
BOX_DEG = 0.75


# (numpy.ndarray times, numpy.ndarray cm)
# least-squares slope in cm/year of a monthly series (NaNs ignored)
def trend_cm_per_year(times, values):
    import numpy as np
    years = (times - times[0]).astype("timedelta64[D]").astype("float64") / 365.25
    ok = np.isfinite(values)
    if ok.sum() < 3:
        return None
    return float(np.polyfit(years[ok], values[ok], 1)[0])


# GRACE provider: fills site.water.storage_anomaly / storage_trend
class GraceProvider(Provider):
    name = "grace"
    title = "GRACE/GRACE-FO JPL mascons RL06.3 v4 (water storage)"
    url = "https://grace.jpl.nasa.gov"
    packages = ("earthaccess", "xarray", "h5netcdf", "numpy")
    credentials = "NASA Earthdata (EARTHDATA_USERNAME/PASSWORD or ~/.netrc)"

    def check(self):
        super().check()
        earthdata_login()

    def fetch(self, area, period, site):
        import earthaccess
        import numpy as np
        import xarray as xr

        granules = earthaccess.search_data(short_name=SHORT_NAME)
        if not granules:
            raise NoData("GRACE mascon file not found")
        ds = xr.open_dataset(earthaccess.open(granules[-1:])[0], engine="h5netcdf")
        lon360 = area.lon % 360                     # the grid uses 0..360 longitudes
        box = ds["lwe_thickness"].sel(lat=slice(area.lat - BOX_DEG, area.lat + BOX_DEG),
                                      lon=slice(lon360 - BOX_DEG, lon360 + BOX_DEG))
        series = box.mean(dim=("lat", "lon"), skipna=True)
        series = series.where(series["time"] <= np.datetime64(period.end), drop=True)
        if series.size == 0 or not np.isfinite(series.values).any():
            raise NoData("no GRACE values here")
        times, cm = series["time"].values, series.values.astype("float64")
        last = int(np.where(np.isfinite(cm))[0][-1])
        month = str(times[last])[:7]
        site.water.storage_anomaly = Measurement(
            float(cm[last]), "cm water", self.name, f"{month}, vs 2004-2009 mean")
        recent = times >= times[last] - np.timedelta64(int(TREND_YEARS * 365.25), "D")
        slope = trend_cm_per_year(times[recent], cm[recent])
        if slope is not None:
            site.water.storage_trend = Measurement(
                slope, "cm/year", self.name,
                f"linear trend {str(times[recent][0])[:7]}..{month}")
