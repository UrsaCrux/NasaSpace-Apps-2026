"""Result types returned by get_site_data."""

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date, datetime


# one value with its unit and where it came from
@dataclass
class Measurement:
    value: float
    unit: str
    source: str
    note: str = ""

    def __str__(self):
        v = f"{self.value:.4g}" if isinstance(self.value, (int, float)) else str(self.value)
        note = f" ({self.note})" if self.note else ""
        return f"{v} {self.unit}".strip() + f"  [{self.source}]{note}"


# air: temperature, humidity, rain, sunlight (ERA5-Land)
@dataclass
class Weather:
    air_temperature: Measurement = None       # period mean, 2 m
    air_temperature_min: Measurement = None
    air_temperature_max: Measurement = None
    dewpoint: Measurement = None
    relative_humidity: Measurement = None
    precipitation: Measurement = None         # total over the period
    solar_radiation: Measurement = None       # mean daily surface irradiation


# soil type, texture, chemistry, water retention, moisture and temperature.
# depth-dependent values are dicts keyed by depth label, e.g. "0-5cm"
@dataclass
class Soil:
    type: Measurement = None                  # WRB reference soil group (SoilGrids)
    type_candidates: list = field(default_factory=list)   # [(name, probability %)]
    clay: dict = field(default_factory=dict)
    sand: dict = field(default_factory=dict)
    silt: dict = field(default_factory=dict)
    organic_carbon: dict = field(default_factory=dict)
    ph: dict = field(default_factory=dict)
    bulk_density: dict = field(default_factory=dict)
    cec: dict = field(default_factory=dict)
    nitrogen: dict = field(default_factory=dict)
    field_capacity: dict = field(default_factory=dict)    # water at -33 kPa
    wilting_point: dict = field(default_factory=dict)     # water at -1500 kPa
    moisture: dict = field(default_factory=dict)          # ERA5-Land, SMAP
    temperature: dict = field(default_factory=dict)       # ERA5-Land, SMAP


# water balance: evapotranspiration, satellite rain, water resources
@dataclass
class Water:
    actual_et: Measurement = None             # WaPOR AETI, mean mm/day
    reference_et: Measurement = None          # WaPOR RET
    transpiration: Measurement = None         # WaPOR T
    evaporation: Measurement = None           # WaPOR E
    precipitation_wapor: Measurement = None   # WaPOR PCP, mean mm/day
    precipitation_satellite: Measurement = None   # GPM IMERG, total mm


# relief from the Copernicus DEM GLO-30
@dataclass
class Terrain:
    elevation: Measurement = None             # mean over the area
    elevation_min: Measurement = None
    elevation_max: Measurement = None
    slope: Measurement = None                 # mean slope


# vegetation productivity
@dataclass
class Vegetation:
    npp: Measurement = None                   # WaPOR net primary production


# active fire detections (NASA FIRMS)
@dataclass
class Fires:
    count: int = None
    nearest_km: float = None
    detections: list = field(default_factory=list)   # dicts: lat, lon, date, frp, confidence


# outcome of one provider: ok, no_data, skipped (not configured), error, planned
@dataclass
class SourceStatus:
    name: str
    status: str
    message: str = ""
    seconds: float = 0.0


# everything get_site_data found for one Area and Period
@dataclass
class SiteData:
    area: object
    period: object
    weather: Weather = field(default_factory=Weather)
    soil: Soil = field(default_factory=Soil)
    water: Water = field(default_factory=Water)
    terrain: Terrain = field(default_factory=Terrain)
    vegetation: Vegetation = field(default_factory=Vegetation)
    fires: Fires = field(default_factory=Fires)
    sources: list = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)

    # ()
    # plain dict (dates as ISO strings), ready for json.dumps
    def to_dict(self):
        return _jsonable(asdict(self))

    # ()
    # human-readable multi-line report of every value found and every source
    def summary(self):
        a, p = self.area, self.period
        lines = [f"Site lon={a.lon:.5f} lat={a.lat:.5f} radius={a.radius_m:g} m, "
                 f"{p.start} .. {p.end}"]
        for section in ("weather", "soil", "water", "terrain", "vegetation"):
            rows = []
            for f in fields(getattr(self, section)):
                v = getattr(getattr(self, section), f.name)
                if isinstance(v, Measurement):
                    rows.append(f"  {f.name}: {v}")
                elif isinstance(v, dict) and v:
                    for k, m in v.items():
                        rows.append(f"  {f.name} {k}: {m}")
                elif isinstance(v, list) and v:
                    rows.append(f"  {f.name}: " + ", ".join(f"{n} {pr}%" for n, pr in v))
            if rows:
                lines += [section.capitalize() + ":"] + rows
        if self.fires.count is not None:
            near = f", nearest {self.fires.nearest_km:.1f} km" if self.fires.count else ""
            lines += ["Fires:", f"  detections: {self.fires.count}{near}"]
        lines.append("Sources:")
        lines += [f"  {s.status:8} {s.name}" + (f": {s.message}" if s.message else "")
                  for s in self.sources]
        return "\n".join(lines)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if is_dataclass(obj):
        return _jsonable(asdict(obj))
    return obj
