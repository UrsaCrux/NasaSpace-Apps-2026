"""Copernicus DEM GLO-30: elevation and slope.

Cloud Optimized GeoTIFF tiles from the public AWS open-data bucket (no key),
30 m resolution; only the pixels around the area are downloaded.
"""

import math

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, circle_mask

TILE_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
            "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
            "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")
# extra margin around the area, in degrees (~2 pixels), so the slope is defined
MARGIN_DEG = 0.0006


# (int lat_floor, int lon_floor)
# URL of the 1x1 degree tile whose south-west corner is (lat_floor, lon_floor)
def tile_url(lat_floor, lon_floor):
    return TILE_URL.format(ns="N" if lat_floor >= 0 else "S", lat=abs(lat_floor),
                           ew="E" if lon_floor >= 0 else "W", lon=abs(lon_floor))


# (tuple bbox)
# URLs of every tile touching a (west, south, east, north) box
def tiles_for(bbox):
    west, south, east, north = bbox
    return [tile_url(la, lo)
            for la in range(math.floor(south), math.floor(north) + 1)
            for lo in range(math.floor(west), math.floor(east) + 1)]


# Copernicus DEM provider: fills site.terrain
class CopernicusDemProvider(Provider):
    name = "copernicus_dem"
    title = "Copernicus DEM GLO-30 (30 m, AWS open data)"
    url = "https://registry.opendata.aws/copernicus-dem/"
    packages = ("rasterio", "numpy")

    def fetch(self, area, period, site):
        import numpy as np
        import rasterio
        from rasterio.errors import RasterioIOError
        from rasterio.merge import merge

        west, south, east, north = area.bbox()
        bbox = (west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG)
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            datasets = []
            try:
                for url in tiles_for(bbox):
                    try:
                        datasets.append(rasterio.open("/vsicurl/" + url))
                    except RasterioIOError:
                        pass            # no tile: open sea
                if not datasets:
                    raise NoData("no DEM tile here (sea)")
                mosaic, transform = merge(datasets, bounds=bbox, nodata=np.nan)
            finally:
                for ds in datasets:
                    ds.close()

        z = mosaic[0].astype("float64")
        rows, cols = np.indices(z.shape)
        lons = transform.c + (cols + 0.5) * transform.a
        lats = transform.f + (rows + 0.5) * transform.e
        mask = circle_mask(lons, lats, area) & np.isfinite(z)
        if not mask.any():
            raise NoData("no elevation values in the area")

        # slope from the elevation gradient, pixel size converted to metres
        dy = abs(transform.e) * 111_320.0
        dx = transform.a * 111_320.0 * math.cos(math.radians(area.lat))
        gy, gx = np.gradient(z, dy, dx)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        slope_ok = mask & np.isfinite(slope)

        t, src = site.terrain, self.name
        t.elevation = Measurement(float(z[mask].mean()), "m", src, "EGM2008 heights")
        t.elevation_min = Measurement(float(z[mask].min()), "m", src)
        t.elevation_max = Measurement(float(z[mask].max()), "m", src)
        if slope_ok.any():
            t.slope = Measurement(float(slope[slope_ok].mean()), "°", src)
