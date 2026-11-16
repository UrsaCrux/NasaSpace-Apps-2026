"""Saved fields (farm plots): one GeoJSON file per field, no Qt or QGIS needed."""

import json
import math
import os
import re
import shutil
import sys
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timezone
from pathlib import Path

from fieldshift.fields.model_inputs import with_model_inputs
from fieldshift.fields.records import dump_records, parse_records
from fieldshift.fields.schema import DEFAULT_COLOR, normalize_color, normalize_data

# root of the repository
REPO_DIR = Path(__file__).resolve().parents[2]

# default folder for saved fields: terrenos/ in the repository root, ignored by
# git. one .geojson per field, named after the field. the
# FIELDSHIFT_FIELDS_DIR environment variable overrides it (tests, demos)
DEFAULT_FIELDS_DIR = REPO_DIR / "terrenos"

# folder used by earlier versions; its files are moved to DEFAULT_FIELDS_DIR
LEGACY_FIELDS_DIR = REPO_DIR / "data" / "local" / "fields"

# fewest vertices a field polygon can have
MIN_VERTICES = 3

# equatorial radius of the WGS84 ellipsoid, in metres
EARTH_RADIUS_M = 6378137.0

# characters not allowed in file names (macOS, Windows, Linux)
_UNSAFE_FILE_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


# a saved field. vertices are (lon, lat) tuples in EPSG:4326, counter-
# clockwise, first vertex not repeated at the end. color is "#rrggbb" (grey
# by default); data maps each key of schema.DATA_FIELDS to
# {"value": ..., "source": "prefilled" | "user"}; records are the dated
# measurements and events (fields.records.Record), oldest first
@dataclass(frozen=True)
class Field:
    name: str
    vertices: tuple
    area_ha: float
    created: str
    path: Path
    color: str = DEFAULT_COLOR
    data: dict = dataclass_field(default_factory=dict)
    records: tuple = ()


# reads and writes the fields of one folder. every field is a GeoJSON file
# with one Feature whose properties hold name, area_ha, created, color and data
class FieldStore:

    # (Path folder = None)
    # uses folder for the files (default: $FIELDSHIFT_FIELDS_DIR, else
    # DEFAULT_FIELDS_DIR); it is created on the first save. with the default
    # folder, fields saved in LEGACY_FIELDS_DIR are moved into it first
    def __init__(self, folder=None):
        folder = folder or os.environ.get("FIELDSHIFT_FIELDS_DIR")
        if not folder:
            migrate_fields(LEGACY_FIELDS_DIR, DEFAULT_FIELDS_DIR)
            folder = DEFAULT_FIELDS_DIR
        self.folder = Path(folder)

    # ()
    # saved fields, oldest first; unreadable files are skipped with a warning
    def fields(self):
        result = []
        for path in sorted(self.folder.glob("*.geojson")):
            try:
                result.append(_read_field(path))
            except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                print(f"warning: skipping field file {path}: {exc}", file=sys.stderr)
        return sorted(result, key=lambda f: (f.created, f.name.casefold()))

    # (str name)
    # the field with this name (case-insensitive), or None
    def get(self, name):
        key = name.strip().casefold()
        return next((f for f in self.fields() if f.name.casefold() == key), None)

    # (str base)
    # first free name of the form "<base> 1", "<base> 2"...
    def suggest_name(self, base):
        taken = {f.name.casefold() for f in self.fields()}
        n = 1
        while f"{base} {n}".casefold() in taken:
            n += 1
        return f"{base} {n}"

    # (str name, str ignore = None)
    # why name cannot be used: "empty", "duplicate", or None when it is fine.
    # the field called ignore (case-insensitive) does not count as a
    # duplicate: pass the field's own name when editing it
    def name_problem(self, name, ignore=None):
        if not name.strip():
            return "empty"
        found = self.get(name)
        if found is not None and (ignore is None
                                  or found.name.casefold() != ignore.strip().casefold()):
            return "duplicate"
        return None

    # (str name, list vertices, str created = None, str color = None, dict data = None)
    # saves a new field from (lon, lat) vertices and returns it. color is
    # grey when None or invalid; data (see schema.py) is completed with
    # prefilled values. raises ValueError for a bad name or fewer than
    # MIN_VERTICES distinct vertices
    def create(self, name, vertices, created=None, color=None, data=None):
        name = name.strip()
        problem = self.name_problem(name)
        if problem:
            raise ValueError(f"invalid field name {name!r}: {problem}")
        ring = _clean_ring(vertices)
        if len(ring) < MIN_VERTICES:
            raise ValueError(f"a field needs at least {MIN_VERTICES} distinct vertices")
        created = created or datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.folder.mkdir(parents=True, exist_ok=True)
        field = Field(name, tuple(ring), round(polygon_area_ha(ring), 4), created,
                      self._free_path(name), normalize_color(color),
                      with_model_inputs(normalize_data(data, ring)))
        collection = {"type": "FeatureCollection", "features": [to_feature(field)]}
        field.path.write_text(json.dumps(collection, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return field

    # (str name, str new_name, str color = None, dict data = None)
    # changes name, colour and data of the saved field called name; None keeps
    # the current colour or data. the file is renamed when the name changes;
    # shape, area and creation date stay. returns the updated Field. raises
    # ValueError when the field does not exist or new_name is empty or taken
    # by another field (the field's own name is fine)
    def update(self, name, new_name, color=None, data=None):
        field = self.get(name)
        if field is None:
            raise ValueError(f"there is no field called {name!r}")
        new_name = new_name.strip()
        problem = self.name_problem(new_name, ignore=field.name)
        if problem:
            raise ValueError(f"invalid field name {new_name!r}: {problem}")
        path = field.path if new_name == field.name else self._free_path(new_name, ignore=field.path)
        updated = replace(
            field, name=new_name, path=path,
            color=field.color if color is None else normalize_color(color),
            data=field.data if data is None else with_model_inputs(
                normalize_data(data, field.vertices)))
        _write(updated)
        if path != field.path and not (field.path.exists() and path.samefile(field.path)):
            field.path.unlink(missing_ok=True)             # renamed: drop the old file
        return updated

    # (str name, tuple records, dict data = None)
    # saves the records (and, when given, the data as it is) of the field
    # called name, keeping its name and file. returns the updated Field
    def save_records(self, name, records, data=None):
        field = self.get(name)
        if field is None:
            raise ValueError(f"there is no field called {name!r}")
        updated = replace(field, records=tuple(sorted(records, key=lambda r: r.time)),
                          data=field.data if data is None else data)
        _write(updated)
        return updated

    # (str name)
    # deletes the field file; returns False when there is no such field
    def delete(self, name):
        field = self.get(name)
        if field is None:
            return False
        field.path.unlink(missing_ok=True)
        return True

    # (str path, list names = None)
    # writes the fields with these names (all when None) to one GeoJSON
    # FeatureCollection (EPSG:4326); returns how many fields were written
    def export(self, path, names=None):
        fields = self.fields()
        if names is not None:
            wanted = {n.strip().casefold() for n in names}
            fields = [f for f in fields if f.name.casefold() in wanted]
        collection = {"type": "FeatureCollection",
                      "features": [to_feature(f) for f in fields]}
        Path(path).write_text(json.dumps(collection, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        return len(fields)

    # (str name, Path ignore = None)
    # unused file path for a field name, made safe for every file system. the
    # file ignore (the field's own, when renaming) counts as free
    def _free_path(self, name, ignore=None):
        stem = _UNSAFE_FILE_CHARS.sub("_", name).strip(" .") or "field"
        path = self.folder / f"{stem}.geojson"
        n = 2
        while path.exists() and not (ignore is not None and path.samefile(ignore)):
            path = self.folder / f"{stem}-{n}.geojson"
            n += 1
        return path


# (Path old_folder, Path new_folder)
# moves the .geojson files of old_folder into new_folder (created if needed)
# and removes old_folder when it ends up empty. a file whose name already
# exists in new_folder stays where it is, with a warning. returns how many
# files were moved
def migrate_fields(old_folder, new_folder):
    old_folder, new_folder = Path(old_folder), Path(new_folder)
    if not old_folder.is_dir():
        return 0
    moved = 0
    for path in sorted(old_folder.glob("*.geojson")):
        target = new_folder / path.name
        if target.exists():
            print(f"warning: {target} already exists; {path} was not moved", file=sys.stderr)
            continue
        new_folder.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target))
        moved += 1
    if moved:
        print(f"info: moved {moved} field file(s) from {old_folder} to {new_folder}",
              file=sys.stderr)
    try:
        old_folder.rmdir()            # only succeeds when empty
    except OSError:
        pass
    return moved


# (Field field)
# GeoJSON Feature (dict) of a field, with a closed polygon ring
def to_feature(field):
    ring = [list(v) for v in field.vertices]
    return {
        "type": "Feature",
        "properties": {"name": field.name, "area_ha": field.area_ha,
                       "created": field.created, "color": field.color,
                       "data": field.data, "records": dump_records(field.records)},
        "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]},
    }


# (list vertices)
# area in hectares of a lon/lat polygon, on a sphere (error well under 1 %)
def polygon_area_ha(vertices):
    n = len(vertices)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        lon_prev = math.radians(vertices[i - 1][0])
        lon_next = math.radians(vertices[(i + 1) % n][0])
        total += (lon_next - lon_prev) * math.sin(math.radians(vertices[i][1]))
    return abs(total) * EARTH_RADIUS_M ** 2 / 2 / 10_000


# (list vertices)
# (lon, lat) float tuples without repeated neighbours or closing vertex,
# turned counter-clockwise as GeoJSON (RFC 7946) recommends
def _clean_ring(vertices):
    ring = []
    for lon, lat in vertices:
        point = (float(lon), float(lat))
        if not ring or point != ring[-1]:
            ring.append(point)
    while len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    signed = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))
    return ring if signed >= 0 else ring[::-1]


# (Path path)
# Field read from a file written by FieldStore. files from before colours and
# data existed open with the grey colour and prefilled data
def _read_field(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    feature = data["features"][0] if data.get("type") == "FeatureCollection" else data
    props = feature["properties"]
    ring = feature["geometry"]["coordinates"][0]
    vertices = tuple((float(x), float(y)) for x, y, *_ in ring[:-1])
    return Field(str(props["name"]), vertices, float(props.get("area_ha", 0.0)),
                 str(props.get("created", "")), path, normalize_color(props.get("color")),
                 normalize_data(props.get("data"), vertices),
                 parse_records(props.get("records")))


# (Field field)
# writes the field's file (through a temporary file: never half-written)
def _write(field):
    collection = {"type": "FeatureCollection", "features": [to_feature(field)]}
    temp = field.path.with_name(field.path.name + ".tmp")
    temp.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, field.path)
