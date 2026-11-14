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


# air during the period: temperature, humidity, rain, sunlight, extremes.
# Filled from ERA5-Land and NASA POWER (see SiteData.weather_by_source)
@dataclass
class Weather:
    air_temperature: Measurement = None       # period mean, 2 m
    air_temperature_min: Measurement = None
    air_temperature_max: Measurement = None
    dewpoint: Measurement = None
    relative_humidity: Measurement = None
    precipitation: Measurement = None         # total over the period
    max_daily_precipitation: Measurement = None   # wettest day
    solar_radiation: Measurement = None       # mean daily surface irradiation
    wind_speed: Measurement = None            # mean, 2 m
    frost_days: Measurement = None            # days with minimum <= 0 °C
    heat_days: Measurement = None             # days with maximum >= HEAT_DAY_C


# temperature from which a day counts as a heat-stress day, °C
HEAT_DAY_C = 35.0


# long-term monthly normals (NASA POWER climatology). Each field is a dict
# keyed "JAN".."DEC" plus "ANN" (annual) -> Measurement
@dataclass
class Climate:
    years: str = ""                           # e.g. "2001-2025"
    temperature: dict = field(default_factory=dict)
    temperature_extreme_max: dict = field(default_factory=dict)
    temperature_extreme_min: dict = field(default_factory=dict)
    precipitation: dict = field(default_factory=dict)        # mm/day
    solar_radiation: dict = field(default_factory=dict)
    relative_humidity: dict = field(default_factory=dict)
    frost_days: dict = field(default_factory=dict)


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
    actual_et_ecostress: Measurement = None   # ECOSTRESS JET, 70 m, mm/day
    actual_et_gldas: Measurement = None       # GLDAS Noah land model, mm/day
    storage_anomaly: Measurement = None       # GRACE/GRACE-FO, latest month, cm water
    storage_trend: Measurement = None         # GRACE/GRACE-FO linear trend, cm/year


# relief from the Copernicus DEM GLO-30
@dataclass
class Terrain:
    elevation: Measurement = None             # mean over the area
    elevation_min: Measurement = None
    elevation_max: Measurement = None
    slope: Measurement = None                 # mean slope


# vegetation vigour and productivity
@dataclass
class Vegetation:
    ndvi: Measurement = None                  # MODIS 16-day NDVI, -1..1
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
    climate: Climate = field(default_factory=Climate)
    # every weather source's own values; `weather` merges them by priority
    weather_by_source: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)

    # (list priority)
    # fills `weather` field by field from weather_by_source, first source in
    # priority order that has the value wins
    def merge_weather(self, priority):
        order = [n for n in priority if n in self.weather_by_source]
        order += [n for n in self.weather_by_source if n not in order]
        for f in fields(Weather):
            for name in order:
                value = getattr(self.weather_by_source[name], f.name)
                if value is not None:
                    setattr(self.weather, f.name, value)
                    break

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
        c = self.climate
        if c.temperature:
            months = [m for m in c.temperature if m != "ANN"]
            lines += [f"Climate normals {c.years} (" + " ".join(m.title() for m in months)
                      + " | year):"]
            for f in fields(Climate):
                d = getattr(c, f.name)
                if isinstance(d, dict) and d:
                    unit = next(iter(d.values())).unit
                    vals = " ".join(f"{d[m].value:.1f}" for m in months if m in d)
                    ann = f" | {d['ANN'].value:.1f}" if "ANN" in d else ""
                    lines.append(f"  {f.name} [{unit}]: {vals}{ann}")
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
