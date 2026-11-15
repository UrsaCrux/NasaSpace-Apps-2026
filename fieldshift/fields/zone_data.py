"""Zone data of a field from the data sources of fieldshift.api.

Each SOURCE_GROUP is one data provider and the DATA_FIELDS keys it fills.
The dialog runs every group in its own thread (fetch_group) and shows each
group's values as soon as it answers, so the slow sources (MODIS can take
30 s) do not hold back the fast ones. Results are cached per place.
"""

import math
import threading
from dataclasses import dataclass

from fieldshift.fields.schema import DATA_FIELDS, WRB_GROUPS, coerce_value

# SoilGrids depths used for the soil data (topsoil, where roots and tillage are)
TOPSOIL = ("0-5cm", "5-15cm", "15-30cm")
# thickness of each of those depths, cm (for depth-weighted means)
TOPSOIL_CM = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
# longest the dialog waits for any source, seconds (each group also has its
# own, shorter, timeout_s)
DEADLINE_S = 80

_cache = {}
_cache_lock = threading.Lock()


# (list vertices)
# fieldshift.api.Area of a polygon: its centroid, and the radius of a circle
# with the same area
def area_of(vertices):
    from fieldshift.api import Area
    from fieldshift.fields.store import polygon_area_ha
    lon = sum(v[0] for v in vertices) / len(vertices)
    lat = sum(v[1] for v in vertices) / len(vertices)
    radius = math.sqrt(max(polygon_area_ha(vertices), 0.0) * 10_000 / math.pi)
    return Area(lon, lat, round(radius, 1))


# (float sand, float silt, float clay)
# USDA texture class key (schema.TEXTURES) from percentages
def usda_texture(sand, silt, clay):
    total = sand + silt + clay
    if total <= 0:
        return None
    sand, silt, clay = (100 * x / total for x in (sand, silt, clay))
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy_sand"
    if clay >= 40:
        if silt >= 40:
            return "silty_clay"
        return "clay" if sand <= 45 else "sandy_clay"
    if clay >= 35 and sand > 45:
        return "sandy_clay"
    if clay >= 27:
        if sand <= 20:
            return "silty_clay_loam"
        return "clay_loam" if sand <= 45 else "sandy_clay_loam"
    if clay >= 20 and sand > 45 and silt < 28:
        return "sandy_clay_loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if silt >= 50:
        return "silt_loam"
    if clay >= 7 and silt >= 28 and sand <= 52:
        return "loam"
    return "sandy_loam"


# (dict by_depth)
# depth-weighted mean over TOPSOIL of {depth: Measurement}, or None
def topsoil_mean(by_depth):
    pairs = [(m.value, TOPSOIL_CM[d]) for d, m in by_depth.items() if d in TOPSOIL_CM]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def _soil(site):
    soil = site.soil
    sand, silt, clay = (topsoil_mean(getattr(soil, k)) for k in ("sand", "silt", "clay"))
    fc, wp = topsoil_mean(soil.field_capacity), topsoil_mean(soil.wilting_point)
    group = soil.type.value.lower() if soil.type else None
    return {
        "soil_texture": usda_texture(sand, silt, clay) if None not in (sand, silt, clay) else None,
        "soil_group": group if group in WRB_GROUPS else None,
        "ph": topsoil_mean(soil.ph),
        "organic_carbon": topsoil_mean(soil.organic_carbon),
        "nitrogen": topsoil_mean(soil.nitrogen),
        "cec": topsoil_mean(soil.cec),
        "available_water": fc - wp if None not in (fc, wp) else None,
    }


def _value(measurement):
    return measurement.value if measurement is not None else None


# one data source for the dialog: the provider to run, how to read the
# DATA_FIELDS keys it fills from the SiteData, and how long the dialog waits
# for it before showing its rows as "not available"
@dataclass(frozen=True)
class SourceGroup:
    name: str
    keys: tuple
    make_provider: object
    extract: object
    timeout_s: float = 30.0
    title: str = ""                 # shown to the user ("SoilGrids")


def _soilgrids():
    from fieldshift.api.providers.soilgrids import SoilGridsProvider
    return SoilGridsProvider(depths=TOPSOIL, properties=(
        "clay", "sand", "silt", "soc", "phh2o", "cec", "nitrogen", "wv0033", "wv1500"))


def _dem():
    from fieldshift.api.providers.copernicus_dem import CopernicusDemProvider
    return CopernicusDemProvider()


def _ndvi():
    from fieldshift.api.providers.modis_ndvi import ModisNdviProvider
    return ModisNdviProvider()


def _wapor():
    from fieldshift.api.providers.wapor import WaporProvider
    return WaporProvider(mapsets=("L1-NPP-D", "L1-AETI-D"))


# the groups, fastest first
SOURCE_GROUPS = (
    SourceGroup("copernicus_dem", ("elevation", "slope"), _dem,
                lambda s: {"elevation": _value(s.terrain.elevation),
                           "slope": _value(s.terrain.slope)}, timeout_s=20,
                title="Copernicus DEM"),
    SourceGroup("wapor", ("npp", "actual_et"), _wapor,
                lambda s: {"npp": _value(s.vegetation.npp),
                           "actual_et": _value(s.water.actual_et)}, timeout_s=30,
                title="FAO WaPOR"),
    SourceGroup("soilgrids", ("soil_texture", "soil_group", "ph", "organic_carbon",
                              "nitrogen", "cec", "available_water"), _soilgrids, _soil,
                timeout_s=40, title="SoilGrids"),
    # the ORNL service answers in ~30 s, or fails after 60 s when overloaded
    SourceGroup("modis_ndvi", ("ndvi",), _ndvi, lambda s: {"ndvi": _value(s.vegetation.ndvi)},
                timeout_s=75, title="MODIS NDVI"),
)

# DATA_FIELDS keys that some group fills (the rest are typed by the farmer)
FETCHED_KEYS = tuple(k for g in SOURCE_GROUPS for k in g.keys)

_SPECS = {spec.key: spec for spec in DATA_FIELDS}


# (SourceGroup group, Area area, Period period = None)
# runs one source for the area and returns {key: valid value or None} for
# the group's keys; raises when the source fails. cached per place
def fetch_group(group, area, period=None):
    from fieldshift.api import Period, SiteData
    period = period or Period.make()
    key = (group.name, round(area.lon, 4), round(area.lat, 4), round(area.radius_m, -1),
           period.start, period.end)
    with _cache_lock:
        if key in _cache:
            return dict(_cache[key])
    provider = group.make_provider()
    provider.check()
    site = SiteData(area, period)
    provider.fetch(area, period, site)
    raw = group.extract(site)
    values = {k: coerce_value(_SPECS[k], raw.get(k)) if raw.get(k) is not None else None
              for k in group.keys}
    with _cache_lock:
        _cache[key] = dict(values)
    return values


# ()
# forgets the cached results (tests, or to force a new download)
def clear_cache():
    with _cache_lock:
        _cache.clear()
