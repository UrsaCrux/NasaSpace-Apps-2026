"""FAO EcoCrop: crop descriptions and ecological requirements.

Data from https://ecocrop.apps.fao.org (no key). The list of all ~2 600
plants (cropListDetails) is downloaded once and cached, so searching is
instant; each crop's page (cropView: description, image, names) and data
sheet (dataSheet: temperature, rain, pH... ranges) are downloaded when asked
and cached too (~/.cache/fieldshift/ecocrop, or $FIELDSHIFT_CACHE).

    from fieldshift.crops import ecocrop
    ecocrop.search("melocoton")[0].name        # 'Prunus persica'
    crop = ecocrop.get_crop("Prunus persica")  # or a synonym, common name, id
    crop.brief, crop.temperature.optimal_min, crop.image_url

From the shell:

    python -m fieldshift.crops.ecocrop peach
    python -m fieldshift.crops.ecocrop --search "vitis"
"""

import html
import json
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field

BASE_URL = "https://ecocrop.apps.fao.org/ecocrop"
LIST_URL = f"{BASE_URL}/srv/en/cropListDetails"
VIEW_URL = BASE_URL + "/srv/en/cropView?id={id}"
SHEET_URL = BASE_URL + "/srv/en/dataSheet?id={id}"
IMAGE_URL = BASE_URL + "/ec_images/{id}.jpg"
# the cached plant list is downloaded again after this many days
INDEX_MAX_AGE_DAYS = 30
# results returned by search()
MAX_RESULTS = 10

_index = None


# one plant of the EcoCrop list
@dataclass(frozen=True)
class IndexEntry:
    id: int
    name: str                       # scientific name
    synonyms: tuple = ()            # other scientific names (varieties, old names)
    common_names: tuple = ()        # in many languages


# optimal and absolute range of a requirement (None where EcoCrop has no value)
@dataclass
class Range:
    optimal_min: float = None
    optimal_max: float = None
    absolute_min: float = None
    absolute_max: float = None


# everything EcoCrop knows about one crop
@dataclass
class CropInfo:
    id: int
    scientific_name: str
    authority: str = ""
    family: str = ""
    synonyms: list = field(default_factory=list)
    common_names: list = field(default_factory=list)
    description: str = ""           # the whole "Notes" text
    sections: dict = field(default_factory=dict)   # "BRIEF DESCRIPTION", "USES"...
    brief: str = ""                 # short description (first section)
    sources: list = field(default_factory=list)
    image_url: str = ""
    url: str = ""
    # data sheet
    life_form: str = ""
    physiology: str = ""
    habit: str = ""
    category: str = ""
    life_span: str = ""
    plant_attributes: str = ""
    temperature: Range = field(default_factory=Range)      # °C
    rainfall: Range = field(default_factory=Range)         # mm/year
    latitude: Range = field(default_factory=Range)         # degrees
    altitude: Range = field(default_factory=Range)         # m
    ph: Range = field(default_factory=Range)
    soil_depth: dict = field(default_factory=dict)         # {"optimal": .., "absolute": ..}
    soil_texture: dict = field(default_factory=dict)
    soil_fertility: dict = field(default_factory=dict)
    soil_salinity: dict = field(default_factory=dict)
    soil_drainage: dict = field(default_factory=dict)
    climate_zone: str = ""
    photoperiod: str = ""
    killing_temp_rest: float = None          # °C
    killing_temp_early_growth: float = None  # °C
    crop_cycle_min: float = None             # days
    crop_cycle_max: float = None
    uses: list = field(default_factory=list)  # [{"use", "detail", "part"}]

    # ()
    # plain dict, ready for json.dumps
    def to_dict(self):
        return asdict(self)

    # (dict data)
    # CropInfo from to_dict() output (the cache)
    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        for key in ("temperature", "rainfall", "latitude", "altitude", "ph"):
            data[key] = Range(**(data.get(key) or {}))
        return cls(**data)


# (str text)
# lower case, no accents, single spaces ("Pêche " -> "peche")
def fold(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(text.split())


def _clean(fragment):
    text = re.sub(r"<br\s*/?>", "\n", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()


def _split_list(text):
    parts = (p.strip() for p in re.split(r",(?![^()]*\))", text))
    return [p for p in parts if p and not re.fullmatch(r"[\d\s().-]+", p)]   # drop "1839"


def _number(text):
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


# -- parsing ----------------------------------------------------------------

# (str page)
# IndexEntry list from the cropListDetails page
def parse_index(page):
    rows = re.findall(r'cropView\?id=(\d+)[^>]*class="serviceLink">(.*?)</a></td>'
                      r'<td>(.*?)</td><td>(.*?)</td>', page, re.S)
    return [IndexEntry(int(i), _clean(name), tuple(_split_list(_clean(syn))),
                       tuple(_split_list(_clean(common))))
            for i, name, syn, common in rows]


# sections used as the short description, best first
BRIEF_SECTIONS = ("BRIEF DESCRIPTION", "DESCRIPTION", "FURTHER INF", "USES", "GROWING PERIOD")
# sections that are not description
NOT_DESCRIPTION = ("SOURCES", "COMMON NAMES")


# (str notes)
# {"BRIEF DESCRIPTION": "...", "USES": "..."} from the Notes text (with
# "\n" for <br>). Headings are upper-case words on their own line, followed
# by two spaces, or followed by a colon: the three layouts exist
def parse_sections(notes):
    lines = []
    for line in notes.splitlines():
        line = line.strip()
        if re.fullmatch(r"[A-Z]{2,}(?: [A-Z]{1,})*", line):
            line += "  "                          # heading alone: mark it like the other layout
        lines.append(line)
    text = " ".join(lines)
    parts = re.split(r"(?:^|(?<=[\s.]))([A-Z]{2,}(?: [A-Z]{1,})*)(?:\s{2,}|:\s+)", text)
    sections = {}
    for i in range(1, len(parts) - 1, 2):
        body = " ".join(parts[i + 1].split())
        if body:
            sections[parts[i].strip()] = body
    return sections


# (str page, int crop_id)
# CropInfo with the cropView data (names, description, image)
def parse_crop_view(page, crop_id):
    name = re.search(r"<h2>(.*?)</h2>", page, re.S)
    labels = dict((_clean(k), _clean(v)) for k, v in re.findall(
        r'<th class="label">(.*?)</th><td>(.*?)</td>', page, re.S))
    notes_raw = re.search(r"Notes\s*</th>\s*<tr>\s*<td>(.*?)</td>", page, re.S)
    sources_raw = re.search(r"Sources\s*</th>\s*<tr>\s*<td>(.*?)</td>", page, re.S)
    image = re.search(r'<img src="(/ecocrop/ec_images/[^"]+)"', page)
    # keep the spacing: in one layout two spaces separate a heading from its text
    notes_text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n",
                                                           notes_raw.group(1)))) if notes_raw else ""
    sections = parse_sections(notes_text)
    sources = [s for s in _clean(sources_raw.group(1)).splitlines() if s] if sources_raw else []
    if not sources and "SOURCES" in sections:   # some pages put them in the notes
        sources = [sections["SOURCES"]]
    described = {k: v for k, v in sections.items() if k not in NOT_DESCRIPTION}
    notes = " ".join(f"{k.capitalize()}: {v}" for k, v in described.items())
    brief = next((sections[k] for k in BRIEF_SECTIONS if k in sections),
                 next(iter(described.values()), ""))
    return CropInfo(
        id=crop_id, scientific_name=_clean(name.group(1)) if name else "",
        authority=labels.get("Authority", ""), family=labels.get("Family", ""),
        synonyms=_split_list(labels.get("Synonyms", "")),
        common_names=_split_list(labels.get("Common names", "")),
        description=notes, sections=sections, brief=brief, sources=sources,
        image_url=(BASE_URL.rsplit("/ecocrop", 1)[0] + image.group(1)) if image else "",
        url=VIEW_URL.format(id=crop_id))


# (str page, CropInfo info)
# adds the dataSheet data (description table, ecology ranges, cultivation,
# uses) to info and returns it
def parse_data_sheet(page, info):
    cells = lambda row: [_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]  # noqa: E731
    rows = [cells(r) for r in re.findall(r"<tr>(.*?)</tr>", page, re.S)]
    pairs = {}
    for row in rows:
        for i in range(0, len(row) - 1, 2):
            if row[i] and row[i] not in pairs:
                pairs[row[i]] = row[i + 1]
    for attr, label in (("life_form", "Life form"), ("physiology", "Physiology"),
                        ("habit", "Habit"), ("category", "Category"),
                        ("life_span", "Life span"), ("plant_attributes", "Plant attributes"),
                        ("climate_zone", "Climate zone"), ("photoperiod", "Photoperiod")):
        setattr(info, attr, pairs.get(label, ""))
    info.killing_temp_rest = _number(pairs.get("Killing temp. during rest"))
    info.killing_temp_early_growth = _number(pairs.get("Killing temp. early growth"))
    ranges = {"Temperat. requir.": "temperature", "Rainfall (annual)": "rainfall",
              "Latitude": "latitude", "Altitude": "altitude", "Soil PH": "ph"}
    soils = {"Soil depth": "soil_depth", "Soil texture": "soil_texture",
             "Soil fertility": "soil_fertility", "Soil salinity": "soil_salinity",
             "Soil drainage": "soil_drainage"}
    for row in rows:
        # ecology rows: label, opt min, opt max, abs min, abs max, soil label, opt, abs
        if row and row[0] in ranges and len(row) >= 5:
            setattr(info, ranges[row[0]], Range(*[_number(v) for v in row[1:5]]))
        for i, cell in enumerate(row):
            if cell in soils and len(row) >= i + 3:
                setattr(info, soils[cell], {"optimal": row[i + 1], "absolute": row[i + 2]})
        if row and row[0] == "Product. system" and len(row) >= 5 and row[2] == "Crop cycle":
            info.crop_cycle_min, info.crop_cycle_max = _number(row[3]), _number(row[4])
    uses = page.split("Used part", 1)
    if len(uses) == 2:
        for row in re.findall(r"<tr>(.*?)</tr>", uses[1], re.S):
            c = cells(row)
            if len(c) == 3 and any(c):
                info.uses.append({"use": c[0], "detail": c[1], "part": c[2]})
    return info


# -- network + cache ----------------------------------------------------------

def _cache():
    from fieldshift.api.providers.base import cache_dir
    return cache_dir("ecocrop")


def _get(url, binary=False):
    import requests
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content if binary else response.text


# (bool refresh = False)
# the list of every EcoCrop plant (cached on disk for INDEX_MAX_AGE_DAYS)
def load_index(refresh=False):
    global _index
    if _index is not None and not refresh:
        return _index
    path = _cache() / "index.json"
    fresh = path.exists() and time.time() - path.stat().st_mtime < INDEX_MAX_AGE_DAYS * 86400
    if fresh and not refresh:
        _index = [IndexEntry(e["id"], e["name"], tuple(e["synonyms"]), tuple(e["common_names"]))
                  for e in json.loads(path.read_text("utf-8"))]
        return _index
    entries = parse_index(_get(LIST_URL))
    if not entries:
        raise RuntimeError("EcoCrop list page could not be read")
    path.write_text(json.dumps([asdict(e) for e in entries], ensure_ascii=False), "utf-8")
    _index = entries
    return _index


# (list entries)
# uses entries as the index (tests, or a list loaded elsewhere)
def set_index(entries):
    global _index
    _index = list(entries) if entries is not None else None


# ()
# the index if it is already in memory (never downloads), else None
def loaded_index():
    return _index


# (str text, int limit = MAX_RESULTS, list index = None)
# plants matching text in their scientific name, synonyms (varieties) or
# common names, ignoring case and accents. Best first: exact name, name
# starting with the text, exact common name, common name starting with the
# text, then names containing it
def search(text, limit=MAX_RESULTS, index=None):
    query = fold(text)
    if len(query) < 2:
        return []
    entries = index if index is not None else load_index()
    scored = []
    for entry in entries:
        sci = [fold(entry.name)] + [fold(s) for s in entry.synonyms]
        common = [fold(c) for c in entry.common_names]
        if query == sci[0]:
            score = 0
        elif any(s.startswith(query) for s in sci):
            score = 1
        elif query in common:
            score = 2
        elif any(c.startswith(query) or f" {query}" in f" {c}" for c in common):
            score = 3
        elif any(query in s for s in sci + common):
            score = 4
        else:
            continue
        scored.append((score, len(entry.name), entry.name, entry))
    return [e for *_, e in sorted(scored, key=lambda s: s[:3])][:limit]


# (str|int name_or_id)
# the IndexEntry for an id, scientific name, synonym or common name, or None
def find(name_or_id, index=None):
    entries = index if index is not None else load_index()
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        return next((e for e in entries if e.id == int(name_or_id)), None)
    results = search(name_or_id, limit=1, index=entries)
    return results[0] if results else None


# (str|int name_or_id, bool data_sheet = True, bool refresh = False)
# CropInfo of a crop (by id, scientific name, variety/synonym or common
# name); raises LookupError when nothing matches. cached on disk
def get_crop(name_or_id, data_sheet=True, refresh=False):
    crop_id = int(name_or_id) if str(name_or_id).isdigit() else None
    if crop_id is None:
        entry = find(name_or_id)
        if entry is None:
            raise LookupError(f"no EcoCrop crop matches {name_or_id!r}")
        crop_id = entry.id
    path = _cache() / f"crop_{crop_id}.json"
    if path.exists() and not refresh:
        return CropInfo.from_dict(json.loads(path.read_text("utf-8")))
    info = parse_crop_view(_get(VIEW_URL.format(id=crop_id)), crop_id)
    if not info.scientific_name:
        raise LookupError(f"EcoCrop has no crop with id {crop_id}")
    if data_sheet:
        parse_data_sheet(_get(SHEET_URL.format(id=crop_id)), info)
    path.write_text(json.dumps(info.to_dict(), ensure_ascii=False), "utf-8")
    return info


# (int crop_id)
# JPEG bytes of the crop's picture (cached), or None when it has none
def get_image(crop_id):
    path = _cache() / f"image_{int(crop_id)}.jpg"
    if path.exists():
        return path.read_bytes() or None
    try:
        data = _get(IMAGE_URL.format(id=int(crop_id)), binary=True)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            path.write_bytes(b"")             # remember: no picture
            return None
        raise
    if not data.startswith(b"\xff\xd8"):      # not a JPEG (error page)
        return None
    path.write_bytes(data)
    return data


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python -m fieldshift.crops.ecocrop",
                                     description="Crop data from FAO EcoCrop.")
    parser.add_argument("name", nargs="?", help="scientific, variety or common name, or id")
    parser.add_argument("--search", metavar="TEXT", help="list the matching plants")
    parser.add_argument("--no-sheet", action="store_true", help="skip the data sheet")
    args = parser.parse_args(argv)
    if args.search:
        for e in search(args.search):
            print(f"{e.id:>7}  {e.name}  ({', '.join(e.common_names[:4])})")
        return 0
    if not args.name:
        parser.error("give a name or --search")
    try:
        info = get_crop(args.name, data_sheet=not args.no_sheet)
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
