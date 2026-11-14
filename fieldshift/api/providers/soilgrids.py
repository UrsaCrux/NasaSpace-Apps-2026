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
        # the two requests are independent: run them at the same time
        with ThreadPoolExecutor(max_workers=2) as pool:
            props_job = pool.submit(get_json, f"{BASE_URL}/properties/query", params={
                "lon": area.lon, "lat": area.lat, "property": list(self.properties),
                "depth": list(self.depths), "value": "mean"})
            cls_job = pool.submit(get_json, f"{BASE_URL}/classification/query",
                                  params={"lon": area.lon, "lat": area.lat,
                                          "number_classes": 3})
            props, cls = props_job.result(), cls_job.result()
        found = parse_properties(props, site.soil, self.name)

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
