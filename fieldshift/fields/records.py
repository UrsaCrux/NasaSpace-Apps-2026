"""Measurements and events a farmer or agronomist records for a field, each
with its date and time: a soil probe reading, a lab pH, the plant height,
the sowing date, a fertiliser dose... They are kept in the field's GeoJSON
file (property "records"), so they travel with it.

A measured value is used instead of the satellite / model one when there is
one (and the UI says it was measured); otherwise the satellite value is
used. Kinds that are also a datum of the field (pH, nitrogen, ...) keep the
field's datum (schema.DATA_FIELDS) up to date with the newest record, so
"Edit field" and the records always agree.

A database (SQLite) could replace the file when there are many records; the
file is enough for now.
"""

from dataclasses import asdict, dataclass
from datetime import datetime

# record kinds: key -> (unit, decimals, DATA_FIELDS key or None, has a value)
KINDS = {
    "soil_moisture": ("% vol", 0, None, True),
    "soil_temp": ("°C", 1, None, True),
    "ph": ("", 1, "ph", True),
    "ec": ("dS/m", 2, None, True),
    "nitrogen": ("g/kg", 2, "nitrogen", True),
    "organic_carbon": ("g/kg", 1, "organic_carbon", True),
    "cec": ("cmol/kg", 1, "cec", True),
    "plant_height": ("cm", 0, None, True),
    "pods": ("", 0, None, True),
    "sowing": ("", 0, None, False),
    "fertilizer": ("kg/ha", 0, None, True),
    "irrigation": ("mm", 0, None, True),
    "harvest": ("kg/ha", 0, None, True),
}
# how a record was made
MEASURED = "measured"          # added as a measurement
EDITED = "edited"              # a value changed in "Edit field"


# one record: time "YYYY-MM-DDTHH:MM" (local), kind (a KINDS key), value
# (None for events such as sowing), a free note, how it was made and, for
# sowing / harvest, the crop id (crops.json) sown or harvested
@dataclass(frozen=True)
class Record:
    time: str
    kind: str
    value: float = None
    note: str = ""
    origin: str = MEASURED
    crop: str = ""

    # ()
    # the date part, "YYYY-MM-DD"
    def date(self):
        return self.time[:10]

    # ()
    # the unit of the kind
    def unit(self):
        return KINDS.get(self.kind, ("",))[0]


# ()
# the current local time as a record time
def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


# (any raw)
# Records read from a file (bad entries are skipped), oldest first
def parse_records(raw):
    records = []
    for item in raw if isinstance(raw, list) else []:
        try:
            kind = str(item["kind"])
            time = str(item["time"])[:16]
            datetime.strptime(time, "%Y-%m-%dT%H:%M")
            value = item.get("value")
            value = None if value is None else float(value)
        except (KeyError, TypeError, ValueError):
            continue
        if kind in KINDS:
            records.append(Record(time, kind, value, str(item.get("note") or ""),
                                  EDITED if item.get("origin") == EDITED else MEASURED,
                                  str(item.get("crop") or "")))
    return tuple(sorted(records, key=lambda r: r.time))


# (tuple records)
# list of plain dicts for the file
def dump_records(records):
    return [asdict(r) for r in records]


# (tuple records, str kind, str date = None)
# the newest record of a kind (on that date "YYYY-MM-DD", when given), or None
def latest(records, kind, date=None):
    found = [r for r in records if r.kind == kind and (date is None or r.date() == date)]
    return found[-1] if found else None


# kinds that name a crop
CROP_KINDS = ("sowing", "harvest")


# (tuple records, str today, int years = 3)
# crop ids sown or harvested in the last years (newest first, no repeats)
def past_crops(records, today, years=3):
    since = f"{int(today[:4]) - years}{today[4:10]}"
    out = []
    for record in reversed(records):
        if record.kind in CROP_KINDS and record.crop and record.time[:10] >= since \
                and record.crop not in out:
            out.append(record.crop)
    return out


# (tuple records, str kind)
# the records of a kind, oldest first
def of_kind(records, kind):
    return [r for r in records if r.kind == kind]
