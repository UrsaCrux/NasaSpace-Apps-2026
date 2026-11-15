"""Search a place or an address by name, with Nominatim (OpenStreetMap).

    from fieldshift.api.geocode import search
    for place in search("Melipilla"):
        place.name, place.lon, place.lat, place.bbox

Nominatim (https://nominatim.openstreetmap.org) needs no key and is free,
but its usage policy applies: at most ONE request per second, an identifying
User-Agent, no autocomplete while typing (the UI searches on Enter) and the
credit ATTRIBUTION wherever results are shown. Data: ODbL. Results are
cached, so repeating a search makes no request.

Chile first: the search runs in Chile and, only if that finds nothing,
anywhere in the world. Standalone, not a Provider: it is not site data.
"""

import threading
import time
from dataclasses import dataclass

from fieldshift import __version__

URL = "https://nominatim.openstreetmap.org/search"
# credit required by the ODbL licence of the data
ATTRIBUTION = "© OpenStreetMap contributors"
# identifies this application to the service (no personal data)
USER_AGENT = f"FieldShift/{__version__} (desktop app for farmers)"
# most results asked for
LIMIT = 5
# country searched first (ISO code); None searches the whole world at once
HOME_COUNTRY = "cl"
# shortest time between two requests, seconds (the service allows one per second)
MIN_INTERVAL_S = 1.1

_cache = {}
_lock = threading.Lock()        # protects the cache and the request clock
_last_request = [0.0]


# a result: name as the service writes it ("Melipilla, Región Metropolitana…"),
# position in degrees, bounding box (xmin, ymin, xmax, ymax) to fit the map
# to it, and the kind of place ("city", "house", "road"...)
@dataclass(frozen=True)
class Place:
    name: str
    lon: float
    lat: float
    bbox: tuple
    kind: str = ""


# (list items)
# Places from a Nominatim jsonv2 answer; items it cannot read are skipped
def parse_places(items):
    places = []
    for item in items:
        try:
            south, north, west, east = (float(v) for v in item["boundingbox"])
            places.append(Place(str(item["display_name"]), float(item["lon"]), float(item["lat"]),
                                (west, south, east, north), str(item.get("type", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return places


# (str text, str country = None)
# one request, waiting first if the last one was less than MIN_INTERVAL_S ago
def _request(text, country):
    from fieldshift.api.providers.base import get_json
    import requests
    with _lock:
        wait = _last_request[0] + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
    params = {"q": text, "format": "jsonv2", "limit": LIMIT, "addressdetails": 0}
    if country:
        params["countrycodes"] = country
    response = requests.get(URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
    response.raise_for_status()
    return response.json()


# (str text)
# up to LIMIT places matching text, Chile first; [] when nothing is found.
# raises when the service cannot be reached
def search(text):
    text = " ".join(text.split())
    if len(text) < 2:
        return []
    key = text.casefold()
    with _lock:
        if key in _cache:
            return list(_cache[key])
    places = parse_places(_request(text, HOME_COUNTRY)) if HOME_COUNTRY else []
    if not places:
        places = parse_places(_request(text, None))
    with _lock:
        _cache[key] = tuple(places)
    return places


# ()
# forgets the cached searches (tests)
def clear_cache():
    with _lock:
        _cache.clear()
    _last_request[0] = 0.0
