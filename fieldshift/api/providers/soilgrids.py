"""ISRIC SoilGrids 2.0: soil type, texture, chemistry and water retention.

REST API v2.0, public, no key (fair use: about 5 requests per minute).
250 m resolution; queried at the centre of the area.
"""

from concurrent.futures import ThreadPoolExecutor

from fieldshift.api.models import Measurement
from fieldshift.api.providers.base import NoData, Provider, get_json

BASE_URL = "https://rest.isric.org/soilgrids/v2.0"
# standard SoilGrids depth intervals
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")
# SoilGrids property -> (Soil field, unit after dividing by d_factor)
PROPERTIES = {
    "clay": ("clay", "%"),
    "sand": ("sand", "%"),
    "silt": ("silt", "%"),
    "soc": ("organic_carbon", "g/kg"),
    "phh2o": ("ph", "pH"),
    "bdod": ("bulk_density", "kg/dm³"),
    "cec": ("cec", "cmol(c)/kg"),
    "nitrogen": ("nitrogen", "g/kg"),
    "wv0033": ("field_capacity", "% vol"),
    "wv1500": ("wilting_point", "% vol"),
}


# SoilGrids provider: fills site.soil (type and all depth-dependent properties)
# properties asked for in one request, and how long each request may take (s)
CHUNK = 3
REQUEST_TIMEOUT_S = 35


class SoilGridsProvider(Provider):
    name = "soilgrids"
    title = "ISRIC SoilGrids 2.0 (250 m)"
    url = "https://rest.isric.org"
    packages = ("requests",)

    # (tuple depths = DEPTHS, tuple properties = all of PROPERTIES)
    # fewer depths / properties make the answer smaller and faster
    def __init__(self, depths=DEPTHS, properties=tuple(PROPERTIES)):
        self.depths = tuple(depths)
        self.properties = tuple(properties)

    def fetch(self, area, period, site):
        # one big properties request often never answers; small ones do. so:
        # CHUNK properties per request, all at the same time. with the
        # classification request that is at most 4 calls for the default 9
        # properties (the service allows 5 per minute). a chunk that fails
        # is skipped: the other values are still used
        chunks = [self.properties[i:i + CHUNK] for i in range(0, len(self.properties), CHUNK)]
        with ThreadPoolExecutor(max_workers=len(chunks) + 1) as pool:
            jobs = [pool.submit(get_json, f"{BASE_URL}/properties/query", params={
                "lon": area.lon, "lat": area.lat, "property": list(chunk),
                "depth": list(self.depths), "value": "mean"}, timeout=REQUEST_TIMEOUT_S)
                for chunk in chunks]
            cls_job = pool.submit(get_json, f"{BASE_URL}/classification/query",
                                  params={"lon": area.lon, "lat": area.lat,
                                          "number_classes": 3}, timeout=REQUEST_TIMEOUT_S)
            found, errors, cls = 0, [], {}
            for job in jobs:
                try:
                    found += parse_properties(job.result(), site.soil, self.name)
                except Exception as exc:
                    errors.append(exc)
            try:
                cls = cls_job.result()
            except Exception as exc:
                errors.append(exc)
        if not found and not cls and errors:
            raise errors[0]                 # nothing answered: report the failure

        if cls.get("wrb_class_name"):
            site.soil.type = Measurement(cls["wrb_class_name"], "WRB", self.name)
            site.soil.type_candidates = [tuple(c) for c in cls.get("wrb_class_probability", [])]
            found += 1
        if not found:
            raise NoData("no soil data at this point (urban, water or rock is masked)")


# (dict response, Soil soil, str source)
# copies a /properties/query response into soil; returns the number of values
def parse_properties(response, soil, source):
    count = 0
    for layer in response.get("properties", {}).get("layers", []):
        if layer["name"] not in PROPERTIES:
            continue
        attr, unit = PROPERTIES[layer["name"]]
        d_factor = layer.get("unit_measure", {}).get("d_factor", 1) or 1
        for depth in layer.get("depths", []):
            value = depth.get("values", {}).get("mean")
            if value is not None:
                getattr(soil, attr)[depth["label"]] = Measurement(value / d_factor, unit, source)
                count += 1
    return count
