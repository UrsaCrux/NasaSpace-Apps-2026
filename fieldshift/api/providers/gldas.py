"""NASA GLDAS-2.1 Noah land model, monthly (0.25°).

Needs a free NASA Earthdata account (earthaccess). Monthly granules are
published ~1-4 months after the month ends: the months overlapping the
period are used, else the latest month (noted).
"""

from datetime import timedelta

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, circle_mask, earthdata_login

SHORT_NAME = "GLDAS_NOAH025_M"
# how far back to look for the latest published month
LOOKBACK_DAYS = 200
# soil layer variable -> (depth label, thickness in m)
SOIL_LAYERS = {
    "SoilMoi0_10cm_inst": ("0-10cm", 0.10),
    "SoilMoi10_40cm_inst": ("10-40cm", 0.30),
    "SoilMoi40_100cm_inst": ("40-100cm", 0.60),
    "SoilMoi100_200cm_inst": ("100-200cm", 1.00),
}
SOIL_TEMPS = {
    "SoilTMP0_10cm_inst": "0-10cm",
    "SoilTMP10_40cm_inst": "10-40cm",
    "SoilTMP40_100cm_inst": "40-100cm",
    "SoilTMP100_200cm_inst": "100-200cm",
}


# GLDAS provider: soil moisture / temperature (4 layers) and ET
class GldasProvider(Provider):
    name = "gldas"
    title = "NASA GLDAS-2.1 Noah monthly (0.25°)"
    url = "https://ldas.gsfc.nasa.gov/gldas"
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
            short_name=SHORT_NAME, version="2.1", bounding_box=area.bbox(min_deg=0.25),
            temporal=(f"{period.start - timedelta(days=LOOKBACK_DAYS)}",
                      f"{period.end}T23:59:59"))
        if not granules:
            raise NoData("no GLDAS months published for this period")

        def month(g):
            return g["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:7]

        inside = [g for g in granules if month(g) >= f"{period.start:%Y-%m}"]
        chosen = inside or sorted(granules, key=month)[-1:]
        note = ("" if inside else "latest month ") + ", ".join(month(g) for g in chosen)

        west, south, east, north = area.bbox(min_deg=0.25)
        sums, counts = {}, {}
        for fobj in earthaccess.open(chosen):
            ds = xr.open_dataset(fobj, engine="h5netcdf").isel(time=0)
            ds = ds.sel(lon=slice(west, east), lat=slice(south, north))
            lons, lats = np.meshgrid(ds["lon"].values, ds["lat"].values)
            mask = circle_mask(lons, lats, area)
            for var in list(SOIL_LAYERS) + list(SOIL_TEMPS) + ["Evap_tavg"]:
                if var in ds:
                    vals = ds[var].transpose("lat", "lon").values[mask]
                    vals = vals[np.isfinite(vals)]
                    if vals.size:
                        sums[var] = sums.get(var, 0.0) + float(vals.mean())
                        counts[var] = counts.get(var, 0) + 1
        if not counts:
            raise NoData("GLDAS has no land cells here")

        mean = {v: sums[v] / counts[v] for v in counts}
        src = self.name
        for var, (depth, thickness) in SOIL_LAYERS.items():
            if var in mean:      # kg/m² of water in the layer -> % of its volume
                site.soil.moisture[f"{depth} GLDAS"] = Measurement(
                    mean[var] / (thickness * 1000) * 100, "% vol", src, note)
        for var, depth in SOIL_TEMPS.items():
            if var in mean:
                site.soil.temperature[f"{depth} GLDAS"] = Measurement(
                    mean[var] - 273.15, "°C", src, note)
        if "Evap_tavg" in mean:  # kg/m²/s -> mm/day
            site.water.actual_et_gldas = Measurement(mean["Evap_tavg"] * 86400, "mm/day",
                                                     src, note)
