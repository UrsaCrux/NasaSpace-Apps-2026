"""NASA ECOSTRESS v003: evapotranspiration (L3T JET) and land surface
temperature (L2T LSTE) at 70 m.

Needs a free NASA Earthdata account. Granules are 110 km tiles (UTM) of
Cloud Optimized GeoTIFFs, acquired at irregular times from the ISS; only the
pixels around the area are read, from up to MAX_GRANULES overpasses in the
period. Cloudy pixels are skipped (LST cloud mask, ET only where valid).
"""

import os

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, earthdata_login

# product -> (short name, file suffix, converter, target)
PRODUCTS = {
    "et": ("ECO_L3T_JET", "_ETdaily.tif", lambda v: v, "mm/day"),
    "lst": ("ECO_L2T_LSTE", "_LST.tif", lambda v: v - 273.15, "°C"),
}
VERSION = "003"
# overpasses read per product
MAX_GRANULES = 5


# (str url, Area area, str token)
# valid pixel values of a COG inside the circle, or an empty list
def read_cog(url, area, token=None, cloud_url=None):
    import numpy as np
    import rasterio
    from rasterio.warp import transform, transform_bounds
    from rasterio.windows import from_bounds

    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR"}
    if token:
        env["GDAL_HTTP_HEADERS"] = f"Authorization: Bearer {token}"
    prefix = "/vsicurl/" if url.startswith("http") else ""
    with rasterio.Env(**env):
        with rasterio.open(prefix + url) as src:
            bounds = transform_bounds("EPSG:4326", src.crs, *area.bbox(min_deg=0.0007))
            window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
            data = src.read(1, window=window, masked=True, boundless=True)
            wt = src.window_transform(window)
            crs = src.crs
        cloud = None
        if cloud_url:
            with rasterio.open(prefix + cloud_url) as csrc:
                cloud = csrc.read(1, window=window, boundless=True, fill_value=1)
    rows, cols = np.indices(data.shape)
    xs = (wt.c + (cols + 0.5) * wt.a).ravel()
    ys = (wt.f + (rows + 0.5) * wt.e).ravel()
    lons, lats = transform(crs, "EPSG:4326", xs, ys)
    inside = np.array([area.contains(lo, la) for lo, la in zip(lons, lats)])
    if not inside.any():          # circle smaller than a pixel: nearest pixel
        d = [area.distance_m(lo, la) for lo, la in zip(lons, lats)]
        inside = np.zeros(len(d), bool)
        inside[int(np.argmin(d))] = True
    valid = ~np.ma.getmaskarray(data).ravel() & np.isfinite(np.asarray(data, "f8").ravel())
    if cloud is not None:
        valid &= (cloud.ravel() == 0)
    return np.asarray(data, "f8").ravel()[inside & valid].tolist()


# ECOSTRESS provider: water.actual_et_ecostress and the LST soil entry
class EcostressProvider(Provider):
    name = "ecostress"
    title = "NASA ECOSTRESS v003 ET + land surface temperature (70 m)"
    url = "https://ecostress.jpl.nasa.gov"
    packages = ("earthaccess", "rasterio", "numpy")
    credentials = "NASA Earthdata (EARTHDATA_USERNAME/PASSWORD or ~/.netrc)"

    def check(self):
        super().check()
        self._auth = earthdata_login()

    def fetch(self, area, period, site):
        import earthaccess

        token = (getattr(self, "_auth", None) and self._auth.token or {}).get("access_token") \
            or os.environ.get("EARTHDATA_TOKEN")
        found = 0
        for key, (short, suffix, conv, unit) in PRODUCTS.items():
            granules = earthaccess.search_data(
                short_name=short, version=VERSION, bounding_box=area.bbox(),
                temporal=(f"{period.start}", f"{period.end}T23:59:59"))[-MAX_GRANULES:]
            values, used = [], 0
            for g in granules:
                links = [u for u in g.data_links(access="external") if u.endswith(".tif")]
                url = next((u for u in links if u.endswith(suffix)), None)
                if not url:
                    continue
                cloud = next((u for u in links if u.endswith("_cloud.tif")), None) \
                    if key == "lst" else None
                vals = read_cog(url, area, token, cloud)
                if vals:
                    values += vals
                    used += 1
            if not values:
                continue
            m = Measurement(conv(sum(values) / len(values)), unit, self.name,
                            f"mean of {used} overpass(es)")
            if key == "et":
                site.water.actual_et_ecostress = m
            else:
                site.soil.temperature["surface ECOSTRESS (LST)"] = m
            found += 1
        if not found:
            raise NoData("no cloud-free ECOSTRESS overpass in the period")
