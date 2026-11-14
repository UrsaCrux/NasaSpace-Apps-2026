"""FAO WaPOR v3 level 1: evapotranspiration, precipitation, biomass.

GISMGR 2.0 REST catalogue (public, no key) + Cloud Optimized GeoTIFFs;
300 m, dekadal (10-day) rasters. Values are daily means over the dekads that
overlap the period; when the period is not published yet the latest dekad is
used and noted.
"""

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, circle_mask, get_json

CATALOG = "https://gismgr.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets"
# WaPOR mapset -> (section, field)
MAPSETS = {
    "L1-AETI-D": ("water", "actual_et"),
    "L1-RET-D": ("water", "reference_et"),
    "L1-T-D": ("water", "transpiration"),
    "L1-E-D": ("water", "evaporation"),
    "L1-PCP-D": ("water", "precipitation_wapor"),
    "L1-NPP-D": ("vegetation", "npp"),
}


# (Period period)
# WaPOR dekad codes overlapping the period, e.g. ["2026-10-D3", "2026-11-D1"]
def dekad_codes(period):
    codes = []
    for day in period.days():
        code = f"{day:%Y-%m}-D{min((day.day - 1) // 10 + 1, 3)}"
        if code not in codes:
            codes.append(code)
    return codes


# WaPOR provider: fills site.water (ET, precipitation) and site.vegetation.npp
class WaporProvider(Provider):
    name = "wapor"
    title = "FAO WaPOR v3 L1 (300 m, dekadal)"
    url = "https://data.apps.fao.org/wapor"
    packages = ("requests", "rasterio", "numpy")

    def fetch(self, area, period, site):
        found = 0
        for mapset, (section, attr) in MAPSETS.items():
            items, note = self._rasters(mapset, period)
            if not items:
                continue
            values = [v for v in (self._read(item, area) for item in items) if v is not None]
            if values:
                unit = items[0]["measureUnit"]
                setattr(getattr(site, section), attr,
                        Measurement(sum(values) / len(values), unit, self.name, note))
                found += 1
        if not found:
            raise NoData("no WaPOR pixels for this area/period")

    # (str mapset, Period period)
    # raster metadata for the period, or the latest raster; returns (items, note)
    def _rasters(self, mapset, period):
        items = []
        for code in dekad_codes(period):
            try:
                items.append(get_json(f"{CATALOG}/{mapset}/rasters/WAPOR-3.{mapset}.{code}")
                             ["response"])
            except Exception:
                pass                    # not published (yet)
        if items:
            return items, ", ".join(i["code"].rsplit(".", 1)[-1] for i in items)
        latest = get_json(f"{CATALOG}/{mapset}/rasters", params={"sort": "code:desc"})
        latest = latest["response"]["items"][:1]
        note = (f"period not published, latest dekad {latest[0]['code'].rsplit('.', 1)[-1]}"
                if latest else "")
        return latest, note

    # (dict item, Area area)
    # mean physical value of one raster over the area, or None
    def _read(self, item, area):
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds

        res = abs(item["affineTransform"][1])
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            with rasterio.open("/vsicurl/" + item["downloadUrl"]) as src:
                window = from_bounds(*area.bbox(min_deg=res), src.transform).round_offsets() \
                    .round_lengths()
                data = src.read(1, window=window, masked=True, boundless=True)
                transform = src.window_transform(window)
        rows, cols = np.indices(data.shape)
        lons = transform.c + (cols + 0.5) * transform.a
        lats = transform.f + (rows + 0.5) * transform.e
        mask = circle_mask(lons, lats, area) & ~np.ma.getmaskarray(data)
        if not mask.any():
            return None
        raw = float(np.asarray(data)[mask].mean())
        return raw * item.get("scale", 1.0) + item.get("offset", 0.0)
