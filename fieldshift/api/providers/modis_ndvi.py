"""MODIS MOD13Q1 NDVI (250 m, 16-day) via the ORNL DAAC subset web service.

Public REST API, no key, but slow (tens of seconds per request), so only one
request is made: the composites from a window ending at the period end.
When no composite overlaps the period yet, the latest one is used and noted.
"""

import math
from datetime import timedelta

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, circle_mask, get_json

API = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MOD13Q1"
BAND = "250m_16_days_NDVI"
# composites are published ~2-4 weeks after they end: look this far back
LOOKBACK_DAYS = 64
# MODIS sinusoidal sphere radius, metres
SIN_R = 6_371_007.181
# the service accepts at most this many km around the point
MAX_KM = 10
# lookback of the reduced retry, days
RETRY_LOOKBACK_DAYS = 32


# (Area area, dict response)
# NDVI values (scaled, valid only) inside the circle for each composite:
# list of (calendar_date, [values])
def parse_subset(response, area):
    import numpy as np
    nrows, ncols = int(response["nrows"]), int(response["ncols"])
    cell = float(response["cellsize"])
    xll, yll = float(response["xllcorner"]), float(response["yllcorner"])
    scale = float(response.get("scale") or 1)
    rows, cols = np.indices((nrows, ncols))
    x = xll + (cols + 0.5) * cell
    y = yll + (nrows - rows - 0.5) * cell          # row 0 is the northern row
    lats = np.degrees(y / SIN_R)
    lons = np.degrees(x / (SIN_R * np.cos(np.radians(lats))))
    mask = circle_mask(lons, lats, area).ravel()
    result = []
    for item in response.get("subset", []):
        data = np.asarray(item["data"], dtype="float64")
        vals = data[mask]
        vals = vals[(vals >= -2000) & (vals <= 10000)] * scale    # fill value -3000
        result.append((item["calendar_date"], vals.tolist()))
    return result


# MODIS NDVI provider: fills site.vegetation.ndvi
class ModisNdviProvider(Provider):
    name = "modis_ndvi"
    title = "MODIS MOD13Q1 NDVI 250 m via ORNL DAAC"
    url = "https://modis.ornl.gov/data/modis_webservice.html"
    packages = ("requests", "numpy")

    def fetch(self, area, period, site):
        km = min(math.ceil(area.radius_m / 1000), MAX_KM)
        reduced = ""
        try:
            response = self._subset(area, period, km, LOOKBACK_DAYS)
        except Exception as exc:
            # the service often fails (502/timeout) on larger requests: retry
            # once with the centre pixel and a shorter window
            if not _is_server_error(exc):
                raise
            response = self._subset(area, period, 0, RETRY_LOOKBACK_DAYS)
            reduced = "; centre pixel only (service overloaded)"
        composites = [(d, v) for d, v in parse_subset(response, area) if v]
        if not composites:
            raise NoData("no valid NDVI composite (clouds or not published yet)")
        # composites covering the period (each spans 16 days from its date)
        inside = [(d, v) for d, v in composites
                  if d >= f"{period.start - timedelta(days=15)}"]
        chosen = inside or composites[-1:]
        values = [x for _, v in chosen for x in v]
        dates = ", ".join(d for d, _ in chosen)
        note = (f"composite(s) {dates}" if inside else f"latest composite {dates}") + reduced
        site.vegetation.ndvi = Measurement(sum(values) / len(values), "NDVI", self.name, note)

    # (Area area, Period period, int km, int lookback_days)
    # one request to the subset service
    def _subset(self, area, period, km, lookback_days):
        start = period.start - timedelta(days=lookback_days)
        return get_json(f"{API}/{PRODUCT}/subset", timeout=120, params={
            "latitude": area.lat, "longitude": area.lon, "band": BAND,
            "startDate": f"A{start:%Y%j}", "endDate": f"A{period.end:%Y%j}",
            "kmAboveBelow": km, "kmLeftRight": km})


# (Exception exc)
# True for HTTP 5xx answers and timeouts / dropped connections
def _is_server_error(exc):
    import requests
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return isinstance(exc, (requests.Timeout, requests.ConnectionError))
