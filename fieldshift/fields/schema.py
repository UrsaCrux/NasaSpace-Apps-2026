"""What is known about a field besides its shape: colour, crop and zone data.

The zone data (soil, relief, vegetation) is described by ONE list,
DATA_FIELDS. To add, remove or change a datum edit that list, add its texts to
the i18n files (keys ``data_fields.<key>``; for a choice also
``data_fields.<key>.<option>``) and, if it comes from a data source, say how in
fieldshift/fields/zone_data.py. The dialog, the data box, the GeoJSON files
and the export all follow the list.

Every datum is stored as ``{"value": ..., "source": ...}`` where source is
"prefilled" (came from satellite or public data), "user" (typed by the
agronomist) or "missing" (no value: the source failed or has no data; value
is None). A datum may also keep ``"prefilled": <value>``, the value the data
source gave, so an edited value can be restored later.

The crop to plant is stored under CROP_KEY as ``{"value": "<variety id>",
"source": "user"}`` (ids from fieldshift/crops/crops.json).
"""

import re
from dataclasses import dataclass

# kinds of datum, and what editor the dialog shows for each
KIND_CHOICE = "choice"     # one of `options`            -> combo box
KIND_NUMBER = "number"     # float in [minimum, maximum] -> text box with a unit
KIND_BOOL = "bool"         # yes / no                    -> combo box

# where a value came from
SOURCE_PREFILLED = "prefilled"
SOURCE_USER = "user"
SOURCE_MISSING = "missing"

# colour of a field when the user does not choose one (grey)
DEFAULT_COLOR = "#9e9e9e"

# key of the crop in the data dict (not part of DATA_FIELDS: it is required
# and the dialog shows it on its own, with a search box)
CROP_KEY = "crop"

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# definition of one datum. key names it in the GeoJSON "data" property and in
# the i18n files. options is for KIND_CHOICE; unit, minimum, maximum and
# decimals are for KIND_NUMBER. group names the section of the dialog
@dataclass(frozen=True)
class DataField:
    key: str
    kind: str
    options: tuple = ()
    unit: str = ""
    minimum: float = 0.0
    maximum: float = 0.0
    decimals: int = 0
    group: str = "soil"


# USDA soil texture classes (from the clay / sand / silt fractions)
TEXTURES = ("sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "silt",
            "sandy_clay_loam", "clay_loam", "silty_clay_loam", "sandy_clay",
            "silty_clay", "clay")

# WRB reference soil groups (SoilGrids uses WRB 2006: Albeluvisols instead of
# Retisols)
WRB_GROUPS = ("acrisols", "albeluvisols", "alisols", "andosols", "anthrosols", "arenosols",
              "calcisols", "cambisols", "chernozems", "cryosols", "durisols", "ferralsols",
              "fluvisols", "gleysols", "gypsisols", "histosols", "kastanozems", "leptosols",
              "lixisols", "luvisols", "nitisols", "phaeozems", "planosols", "plinthosols",
              "podzols", "regosols", "retisols", "solonchaks", "solonetz", "stagnosols",
              "technosols", "umbrisols", "vertisols")

# the zone data, in the order the dialog shows it: soil (SoilGrids, top
# 30 cm), relief (Copernicus DEM), vegetation (MODIS, WaPOR) and what only the
# farmer knows. No weather here: that belongs to the analyses
DATA_FIELDS = (
    DataField("soil_texture", KIND_CHOICE, options=TEXTURES),
    DataField("soil_group", KIND_CHOICE, options=WRB_GROUPS),
    DataField("ph", KIND_NUMBER, minimum=3.0, maximum=10.0, decimals=1),
    DataField("organic_carbon", KIND_NUMBER, unit="g/kg", maximum=600, decimals=1),
    DataField("nitrogen", KIND_NUMBER, unit="g/kg", maximum=50, decimals=2),
    DataField("cec", KIND_NUMBER, unit="cmol/kg", maximum=200, decimals=1),
    DataField("available_water", KIND_NUMBER, unit="% vol", maximum=60, decimals=1),
    DataField("elevation", KIND_NUMBER, unit="m", minimum=-500, maximum=9000, decimals=0,
              group="relief"),
    DataField("slope", KIND_NUMBER, unit="°", maximum=90, decimals=1, group="relief"),
    DataField("ndvi", KIND_NUMBER, minimum=-1.0, maximum=1.0, decimals=2, group="vegetation"),
    DataField("npp", KIND_NUMBER, unit="gC/m²/day", maximum=30, decimals=2, group="vegetation"),
    DataField("actual_et", KIND_NUMBER, unit="mm/day", maximum=20, decimals=1,
              group="vegetation"),
    DataField("irrigated", KIND_BOOL, group="farm"),
)

# group order and the i18n key of each group title
GROUPS = ("soil", "relief", "vegetation", "farm")


# (str text)
# "#rrggbb" in lower case; DEFAULT_COLOR when text is not a colour like that
def normalize_color(text):
    if isinstance(text, str) and _COLOR_RE.match(text.strip()):
        return text.strip().lower()
    return DEFAULT_COLOR


# (DataField spec, any raw)
# raw as a valid value of this datum, or None when it is not one
def coerce_value(spec, raw):
    if spec.kind == KIND_CHOICE:
        return raw if raw in spec.options else None
    if spec.kind == KIND_BOOL:
        return raw if isinstance(raw, bool) else None
    if spec.kind == KIND_NUMBER and isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if spec.minimum <= raw <= spec.maximum:
            return round(float(raw), spec.decimals)
    return None


# ()
# data with every datum missing (and no crop): what a new field starts with
# before the data sources answer
def empty_data():
    data = {spec.key: {"value": None, "source": SOURCE_MISSING} for spec in DATA_FIELDS}
    data[CROP_KEY] = {"value": None, "source": SOURCE_MISSING}
    return data


# (any raw, list vertices = None)
# raw (data read from a file or from the dialog) as a complete, valid data
# dict: unknown keys are dropped and a missing or invalid datum becomes
# "missing", so files without data (or from older versions) still open
def normalize_data(raw, vertices=None):
    from fieldshift.crops import is_variety
    data = empty_data()
    if not isinstance(raw, dict):
        return data
    for spec in DATA_FIELDS:
        item = raw.get(spec.key)
        value = coerce_value(spec, item.get("value")) if isinstance(item, dict) else None
        original = coerce_value(spec, item.get("prefilled")) if isinstance(item, dict) else None
        if value is not None:
            source = SOURCE_USER if item.get("source") == SOURCE_USER else SOURCE_PREFILLED
            data[spec.key] = {"value": value, "source": source}
        if original is not None:
            data[spec.key]["prefilled"] = original
        elif value is not None and data[spec.key]["source"] == SOURCE_PREFILLED:
            data[spec.key]["prefilled"] = value
    crop = raw.get(CROP_KEY)
    if isinstance(crop, dict) and is_variety(crop.get("value")):
        data[CROP_KEY] = {"value": crop["value"], "source": SOURCE_USER}
    return data
