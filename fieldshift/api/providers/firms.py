"""NASA FIRMS: active fire detections (VIIRS 375 m).

Needs a free MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/map_key/) in
FIRMS_MAP_KEY. Near-real-time data covers the last ~2 months; older periods
use the standard-processing archive. At most 10 days per request (the API
limit): the last 10 days of the period.
"""

import csv
import io
import os
from datetime import date, timedelta

from fieldshift.api.providers.base import Provider, ProviderUnavailable, get_text

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
# FIRMS accepts at most this many days per request
MAX_DAYS = 10


# FIRMS provider: fills site.fires
class FirmsProvider(Provider):
    name = "firms"
    title = "NASA FIRMS active fires (VIIRS S-NPP)"
    url = "https://firms.modaps.eosdis.nasa.gov"
    packages = ("requests",)
    credentials = "FIRMS_MAP_KEY"

    def check(self):
        super().check()
        if not os.environ.get("FIRMS_MAP_KEY"):
            raise ProviderUnavailable("no FIRMS_MAP_KEY environment variable")

    def fetch(self, area, period, site):
        days = min(len(period), MAX_DAYS)
        start = period.end - timedelta(days=days - 1)
        source = ("VIIRS_SNPP_NRT" if (date.today() - period.end).days <= 60
                  else "VIIRS_SNPP_SP")
        west, south, east, north = area.bbox()
        url = (f"{API}/{os.environ['FIRMS_MAP_KEY']}/{source}/"
               f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}/{days}/{start}")
        text = get_text(url)
        if text.lstrip().lower().startswith(("invalid", "error")):
            raise RuntimeError(text.strip()[:200])

        detections = []
        for row in csv.DictReader(io.StringIO(text)):
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if area.contains(lon, lat):
                detections.append({"lat": lat, "lon": lon, "date": row.get("acq_date"),
                                   "frp": float(row.get("frp") or 0),
                                   "confidence": row.get("confidence")})
        f = site.fires
        f.detections = detections
        f.count = len(detections)
        f.nearest_km = (min(area.distance_m(d["lon"], d["lat"]) for d in detections) / 1000
                        if detections else None)
