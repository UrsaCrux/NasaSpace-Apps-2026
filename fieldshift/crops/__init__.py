"""Catalogue of crops and varieties, and the search used by the field dialog.

The catalogue is crops.json next to this module. PLACEHOLDER: the varieties
are made-up ("variety 1", "variety 2"...) until the real list is decided.
Each crop has a name per language and optional aliases; each variety has an
id ("peach.v1") that is what a field stores.

    search("duraz")   -> [Variety(id="peach.v1", ...), ...]   # in Spanish too
    label("peach.v1") -> "Peach – variety 1" / "Durazno – variedad 1"

A field may also store any plant of FAO EcoCrop (fieldshift.crops.ecocrop)
as "ecocrop:<id>" ("ecocrop:1796"); each catalogue crop names its EcoCrop
plant ("ecocrop": scientific name), used for the description and picture.
"""

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from fieldshift.i18n import language, tr

# the catalogue file
CATALOG_PATH = Path(__file__).resolve().parent / "crops.json"
# results shown in the search dropdown
MAX_RESULTS = 12
# prefix of the ids of EcoCrop plants chosen directly
ECOCROP_PREFIX = "ecocrop:"

_catalog = None


# one variety of a crop, as returned by search()
@dataclass(frozen=True)
class Variety:
    id: str
    crop: str
    number: int


# (str text)
# lower case, without accents and surrounding spaces ("Melocotón " -> "melocoton")
def fold(text):
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def _load():
    global _catalog
    if _catalog is None:
        _catalog = json.loads(CATALOG_PATH.read_text("utf-8"))["crops"]
    return _catalog


def _crop(crop_id):
    return next((c for c in _load() if c["id"] == crop_id), None)


# (str crop_id)
# crop name in the current language (English when missing)
def crop_name(crop_id):
    crop = _crop(crop_id)
    if crop is None:
        return crop_id
    return crop["names"].get(language()) or crop["names"]["en"]


# (str variety_id)
# "Peach – variety 1" in the current language; for an EcoCrop plant its
# scientific name (when the EcoCrop list is loaded); the id itself when unknown
def label(variety_id):
    eco = ecocrop_number(variety_id)
    if eco is not None:
        from fieldshift.crops import ecocrop
        entry = next((e for e in ecocrop.loaded_index() or () if e.id == eco), None)
        return entry.name if entry else tr("crops.ecocrop_label", id=eco)
    variety = variety_by_id(variety_id)
    if variety is None:
        return str(variety_id)
    name = variety_name(variety_id)
    if name:
        return tr("crops.variety_named", crop=crop_name(variety.crop), name=name)
    return tr("crops.variety_label", crop=crop_name(variety.crop), number=variety.number)


# (str variety_id)
# the cultivar name of a catalogue variety ("Cabernet Sauvignon"), or None
# when the catalogue only numbers it
def variety_name(variety_id):
    variety = variety_by_id(variety_id)
    if variety is None:
        return None
    names = _crop(variety.crop).get("variety_names") or []
    return names[variety.number - 1] if variety.number <= len(names) else None


# (any value)
# the EcoCrop id of an "ecocrop:<id>" value, or None
def ecocrop_number(value):
    if isinstance(value, str) and value.startswith(ECOCROP_PREFIX):
        rest = value[len(ECOCROP_PREFIX):]
        return int(rest) if rest.isdigit() else None
    return None


# (str variety_id)
# scientific name of the EcoCrop plant behind a catalogue variety (or None);
# for "ecocrop:<id>" values use ecocrop_number
def ecocrop_name(variety_id):
    variety = variety_by_id(variety_id)
    crop = _crop(variety.crop) if variety else None
    return crop.get("ecocrop") if crop else None


# (str scientific_name)
# id of the first catalogue crop linked to this EcoCrop plant, or None
def crop_for_ecocrop(scientific_name):
    return next((c["id"] for c in _load() if c.get("ecocrop") == scientific_name), None)


# (str crop_id)
# every Variety of a catalogue crop
def varieties(crop_id):
    crop = _crop(crop_id)
    return [Variety(f"{crop_id}.v{n}", crop_id, n)
            for n in range(1, crop["varieties"] + 1)] if crop else []


# (str variety_id)
# the Variety with this id, or None
def variety_by_id(variety_id):
    if not isinstance(variety_id, str) or "." not in variety_id:
        return None
    crop_id, _, rest = variety_id.partition(".")
    crop = _crop(crop_id)
    if crop is None or not rest.startswith("v") or not rest[1:].isdigit():
        return None
    number = int(rest[1:])
    return Variety(variety_id, crop_id, number) if 1 <= number <= crop["varieties"] else None


# (any variety_id)
# True for an id of the catalogue or an "ecocrop:<id>" value
def is_variety(variety_id):
    return variety_by_id(variety_id) is not None or ecocrop_number(variety_id) is not None


# (str text, int limit = MAX_RESULTS)
# varieties of the crops whose name (any language) or alias matches text,
# ignoring case and accents. crops whose name starts with the text come
# first, then names containing it; a trailing number ("peach 2") narrows to
# that variety, and extra trailing words ("peach – variety 2") are dropped
# until something matches. empty text gives nothing
def search(text, limit=MAX_RESULTS):
    words = fold(text).replace("–", " ").replace("-", " ").split()
    if not words:
        return []
    query = " ".join(words)
    named = [Variety(f"{crop['id']}.v{n}", crop["id"], n) for crop in _load()
             for n, name in enumerate(crop.get("variety_names") or [], start=1)
             if fold(name).startswith(query) or f" {query}" in f" {fold(name)}"]
    if named:
        return named[:limit]                       # a cultivar name: just those
    number = int(words[-1]) if len(words) > 1 and words[-1].isdigit() else None
    if number is not None:
        words = words[:-1]
    ranked = []
    while words and not ranked:
        ranked = _rank(" ".join(words))
        words = words[:-1]
    results = []
    for _, _, crop in sorted(ranked, key=lambda r: r[:2]):
        for n in range(1, crop["varieties"] + 1):
            if number is None or n == number:
                results.append(Variety(f"{crop['id']}.v{n}", crop["id"], n))
    return results[:limit]


# (str query)
# [(rank, name, crop)] of the crops matching a folded query
def _rank(query):
    ranked = []
    for crop in _load():
        names = [fold(n) for n in crop["names"].values()]
        names += [fold(a) for aliases in crop.get("aliases", {}).values() for a in aliases]
        current = fold(crop["names"].get(language()) or crop["names"]["en"])
        if any(n.startswith(query) for n in names):
            rank = 0 if current.startswith(query) else 1
        elif any(query in n for n in names):
            rank = 2
        else:
            continue
        ranked.append((rank, crop_name(crop["id"]).lower(), crop))
    return ranked
