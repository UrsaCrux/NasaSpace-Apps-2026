"""User-visible texts in several languages.

Every text the user reads lives in a JSON file next to this module, one file
per language (``en.json``, ``es.json``...). Code never writes the text
itself, it asks for it by key::

    from fieldshift.i18n import tr
    button = QtWidgets.QPushButton(tr("fields.draw"))
    tr("fields.export_done", count=3, path="/tmp/f.geojson")

The language comes from the ``FIELDSHIFT_LANG`` environment variable
(default ``en``) or from :func:`set_language`. Missing keys fall back to
English, then to the key itself, so a half-translated file never crashes.
"""

import json
import os
import sys
from pathlib import Path

# folder with one <language code>.json file per language
LOCALES_DIR = Path(__file__).resolve().parent

# language used when no other is chosen, and as fallback for missing keys
DEFAULT_LANGUAGE = "en"

_texts = {}                  # language code -> {key: text}
_language = DEFAULT_LANGUAGE


# ()
# language codes that have a JSON file, sorted ("en", "es", ...)
def available_languages():
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


# ()
# code of the language in use
def language():
    return _language


# (str code)
# switches the language of the texts asked for from now on; widgets already
# built keep their text. raises ValueError for a language without a file
def set_language(code):
    global _language
    if code not in available_languages():
        raise ValueError(f"no texts for language {code!r} in {LOCALES_DIR}")
    _language = code


# (str key, **values)
# text for key in the current language, with {placeholders} filled from values
def tr(key, **values):
    text = _load(_language).get(key)
    if text is None:
        text = _load(DEFAULT_LANGUAGE).get(key, key)
    return text.format(**values) if values else text


# (str code)
# {key: text} of one language, read once and cached
def _load(code):
    if code not in _texts:
        path = LOCALES_DIR / f"{code}.json"
        try:
            _texts[code] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"warning: cannot read texts {path}: {exc}", file=sys.stderr)
            _texts[code] = {}
    return _texts[code]


_env_language = os.environ.get("FIELDSHIFT_LANG")
if _env_language:
    try:
        set_language(_env_language)
    except ValueError as exc:
        print(f"warning: {exc}; using {DEFAULT_LANGUAGE!r}", file=sys.stderr)
