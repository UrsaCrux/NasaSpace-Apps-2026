"""NASA SMAP L4 SPL4SMGP v8: surface and root-zone soil moisture.

Needs a free NASA Earthdata account (earthaccess). 9 km, 3-hourly global
granules; only the few cells around the area are read over HTTP, from up to
MAX_GRANULES granules spread over the period.
"""

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, earthdata_login

SHORT_NAME = "SPL4SMGP"
# granules sampled over the period (each is a global 3-hour snapshot)
MAX_GRANULES = 4
# Geophysical_Data variable -> (Soil field, key, converter, unit)
VARIABLES = {
    "sm_surface": ("moisture", "0-5cm SMAP", lambda v: v * 100, "% vol"),
    "sm_rootzone": ("moisture", "0-100cm SMAP", lambda v: v * 100, "% vol"),
    "soil_temp_layer1": ("temperature", "0-10cm SMAP", lambda v: v - 273.15, "°C"),
    "surface_temp": ("temperature", "surface SMAP", lambda v: v - 273.15, "°C"),
}


# SMAP provider: adds SMAP entries to site.soil.moisture / temperature
class SmapProvider(Provider):
    name = "smap_l4"
    title = "NASA SMAP L4 soil moisture SPL4SMGP v8 (9 km)"
    url = "https://nsidc.org/data/spl4smgp"
    packages = ("earthaccess", "h5py", "numpy")
    credentials = "NASA Earthdata (EARTHDATA_USERNAME/PASSWORD or ~/.netrc)"

    def check(self):
        super().check()
        earthdata_login()

    def fetch(self, area, period, site):
        import earthaccess
        import h5py
        import numpy as np

        granules = earthaccess.search_data(
            short_name=SHORT_NAME, bounding_box=area.bbox(),
            temporal=(f"{period.start}", f"{period.end}T23:59:59"))
        if not granules:
            raise NoData("no SMAP granules for the period (not published yet?)")
        step = max(len(granules) // MAX_GRANULES, 1)
        files = earthaccess.open(granules[::step][:MAX_GRANULES])

        values = {v: [] for v in VARIABLES}
        for fobj in files:
            with h5py.File(fobj, "r") as f:
                lat_col = f["cell_lat"][:, 0]
                lon_row = f["cell_lon"][0, :]
                west, south, east, north = area.bbox()
                rows = np.where((lat_col >= south) & (lat_col <= north))[0]
                cols = np.where((lon_row >= west) & (lon_row <= east))[0]
                if rows.size == 0:
                    rows = np.array([np.abs(lat_col - area.lat).argmin()])
                if cols.size == 0:
                    cols = np.array([np.abs(lon_row - area.lon).argmin()])
                r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
                for var in VARIABLES:
                    block = f["Geophysical_Data"][var][r0:r1, c0:c1].astype("float64")
                    block = block[block > -9000]        # fill value -9999
                    if block.size:
                        values[var].append(block.mean())

        found = 0
        for var, (attr, key, conv, unit) in VARIABLES.items():
            if values[var]:
                getattr(site.soil, attr)[key] = Measurement(
                    conv(float(np.mean(values[var]))), unit, self.name,
                    f"mean of {len(values[var])} granule(s)")
                found += 1
        if not found:
            raise NoData("SMAP has no valid cells here")
