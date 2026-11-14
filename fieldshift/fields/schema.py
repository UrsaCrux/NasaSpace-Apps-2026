"""What is known about a field besides its shape: colour and zone data.

The zone data (soil, rain...) is described by ONE list, DATA_FIELDS. To add,
remove or change a datum edit that list and add its texts to the i18n files
(keys ``data_fields.<key>``; for a choice also ``data_fields.<key>.<option>``).
Nothing else needs to change: the dialog, the data box, the GeoJSON files and
the export all follow the list.

Every datum is stored as ``{"value": ..., "source": "prefilled" | "user"}``:
"prefilled" came from satellite or public data, "user" was typed by the
agronomist, who may always go back to the prefilled value.
"""

import hashlib
import re
from dataclasses import dataclass

# kinds of datum, and what editor the dialog shows for each
KIND_CHOICE = "choice"     # one of `options`            -> combo box
KIND_NUMBER = "number"     # float in [minimum, maximum] -> spin box
KIND_BOOL = "bool"         # yes / no                    -> combo box

# where a value came from
SOURCE_PREFILLED = "prefilled"
SOURCE_USER = "user"

# colour of a field when the user does not choose one (grey)
DEFAULT_COLOR = "#9e9e9e"

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# definition of one datum. key names it in the GeoJSON "data" property and in
# the i18n files. options is for KIND_CHOICE; unit, minimum, maximum and
# decimals are for KIND_NUMBER
@dataclass(frozen=True)
class DataField:
    key: str
    kind: str
    options: tuple = ()
    unit: str = ""
    minimum: float = 0.0
    maximum: float = 0.0
    decimals: int = 0


# PLACEHOLDER LIST: these four data are only examples. The final list has not
# been decided; edit it here (and in the i18n files) when it is
DATA_FIELDS = (
    DataField("soil_type", KIND_CHOICE, options=("clay", "loam", "sand", "silt")),
    DataField("ph", KIND_NUMBER, minimum=3.0, maximum=10.0, decimals=1),
    DataField("annual_rain_mm", KIND_NUMBER, unit="mm", minimum=0, maximum=8000, decimals=0),
    DataField("irrigated", KIND_BOOL),
)


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


# (list vertices)
# the prefilled data of a field: {key: {"value": ..., "source": "prefilled"}}
# for every entry of DATA_FIELDS, looked up at the centre of the polygon
def prefill_data(vertices):
    lon = sum(v[0] for v in vertices) / len(vertices)
    lat = sum(v[1] for v in vertices) / len(vertices)
    return {spec.key: {"value": _lookup_zone_value(spec, lon, lat), "source": SOURCE_PREFILLED}
            for spec in DATA_FIELDS}


# (any raw, list vertices)
# raw (data read from a file or from the dialog) as a complete, valid data
# dict: unknown keys are dropped, and a missing or invalid datum gets its
# prefilled value. so files without data still open
def normalize_data(raw, vertices):
    data = prefill_data(vertices)
    if not isinstance(raw, dict):
        return data
    for spec in DATA_FIELDS:
        item = raw.get(spec.key)
        value = coerce_value(spec, item.get("value")) if isinstance(item, dict) else None
        if value is not None:
            source = SOURCE_USER if item.get("source") == SOURCE_USER else SOURCE_PREFILLED
            data[spec.key] = {"value": value, "source": source}
    return data


# ---------------------------------------------------------------------------
# PLACEHOLDER: fake values. The real version will ask satellite / public data
# (SoilGrids for soil, NASA POWER for rain...) for the point (lon, lat) and
# return the real value; replace the body of _lookup_zone_value and delete
# everything below it. Fake values come from a hash of the rounded
# coordinates, so a place always gets the same ones.

_PLACEHOLDER_RANGE = {"ph": (5.5, 8.0), "annual_rain_mm": (150, 1600)}


# (DataField spec, float lon, float lat)
# PLACEHOLDER: a made-up value for this datum at this point
def _lookup_zone_value(spec, lon, lat):
    seed = f"{spec.key}:{lon:.2f}:{lat:.2f}".encode()
    n = int.from_bytes(hashlib.sha256(seed).digest()[:4], "big")
    if spec.kind == KIND_CHOICE:
        return spec.options[n % len(spec.options)]
    if spec.kind == KIND_BOOL:
        return n % 2 == 0
    low, high = _PLACEHOLDER_RANGE.get(spec.key, (spec.minimum, spec.maximum))
    return round(low + (n % 1001) / 1000 * (high - low), spec.decimals)
