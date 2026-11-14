"""Area (centre + radius) and Period (date range) of a query."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

# mean Earth radius in metres (same value as the C++ core)
EARTH_RADIUS_M = 6_371_008.8
# metres per degree of latitude
M_PER_DEG = 111_320.0


# (float lat1, float lon1, float lat2, float lon2)
# great-circle distance in metres between two points in degrees
def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


# circle on the ground: centre in degrees (EPSG:4326), radius in metres
@dataclass(frozen=True)
class Area:
    lon: float
    lat: float
    radius_m: float = 1000.0

    def __post_init__(self):
        if not -180 <= self.lon <= 180 or not -90 <= self.lat <= 90:
            raise ValueError(f"invalid position lon={self.lon} lat={self.lat}")
        if self.radius_m < 0:
            raise ValueError("radius_m must be >= 0")

    # (float min_deg = 0)
    # (west, south, east, north) box around the circle, at least min_deg wide
    # on each side of the centre (raster sources need a few pixels)
    def bbox(self, min_deg=0.0):
        dlat = max(self.radius_m / M_PER_DEG, min_deg)
        dlon = max(self.radius_m / (M_PER_DEG * max(math.cos(math.radians(self.lat)), 1e-6)),
                   min_deg)
        return (max(self.lon - dlon, -180.0), max(self.lat - dlat, -90.0),
                min(self.lon + dlon, 180.0), min(self.lat + dlat, 90.0))

    # (float lon, float lat)
    # True when the point is inside the circle
    def contains(self, lon, lat):
        return haversine_m(self.lat, self.lon, lat, lon) <= self.radius_m

    # (float lon, float lat)
    # distance in metres from the centre
    def distance_m(self, lon, lat):
        return haversine_m(self.lat, self.lon, lat, lon)


# inclusive date range. Default: the 7 days ending a week ago, because
# reanalysis and satellite products are published with a few days of delay
@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(f"period end {self.end} is before start {self.start}")

    # (date|str start = None, date|str end = None, int days = 7, int lag_days = 7)
    # builds a Period from dates or "YYYY-MM-DD" strings, filling what is missing
    @classmethod
    def make(cls, start=None, end=None, days=7, lag_days=7):
        end = _to_date(end) if end else date.today() - timedelta(days=lag_days)
        start = _to_date(start) if start else end - timedelta(days=days - 1)
        return cls(start, end)

    # ()
    # list of every date in the period
    def days(self):
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)]

    def __len__(self):
        return (self.end - self.start).days + 1


def _to_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))
