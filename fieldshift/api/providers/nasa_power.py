"""NASA POWER: daily agro-meteorology and long-term monthly climate normals.

Public REST API, no key. ~0.5° (MERRA-2 / CERES based), daily values up to a
few days ago; climatology from a pre-computed multi-year period.
"""

from fieldshift.api.models import HEAT_DAY_C, Measurement, Weather
from fieldshift.api.providers.base import NoData, Provider, get_json

API = "https://power.larc.nasa.gov/api/temporal"
DAILY = ["T2M", "T2M_MIN", "T2M_MAX", "T2MDEW", "RH2M", "PRECTOTCORR",
         "ALLSKY_SFC_SW_DWN", "WS2M", "GWETTOP", "GWETROOT", "TS"]
CLIMATE = ["T2M", "T2M_MIN", "T2M_MAX", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN", "RH2M",
           "FROST_DAYS"]
# POWER climatology parameter -> (Climate field, unit)
CLIMATE_FIELDS = {
    "T2M": ("temperature", "°C"),
    "T2M_MAX": ("temperature_extreme_max", "°C"),
    "T2M_MIN": ("temperature_extreme_min", "°C"),
    "PRECTOTCORR": ("precipitation", "mm/day"),
    "ALLSKY_SFC_SW_DWN": ("solar_radiation", "MJ/m²/day"),
    "RH2M": ("relative_humidity", "%"),
    "FROST_DAYS": ("frost_days", "days"),
}


# (dict response, str parameter)
# list of the daily values of one parameter, fill values (-999) removed
def daily_values(response, parameter):
    fill = response.get("header", {}).get("fill_value", -999.0)
    values = response["properties"]["parameter"].get(parameter, {}).values()
    return [v for v in values if v is not None and v != fill]


# NASA POWER provider: weather_by_source["nasa_power"], climate normals and
# soil wetness / skin temperature
class NasaPowerProvider(Provider):
    name = "nasa_power"
    title = "NASA POWER daily agro-meteorology + climatology (~0.5°)"
    url = "https://power.larc.nasa.gov"
    packages = ("requests",)

    def fetch(self, area, period, site):
        daily = get_json(f"{API}/daily/point", timeout=90, params={
            "parameters": ",".join(DAILY), "community": "AG", "format": "JSON",
            "longitude": area.lon, "latitude": area.lat,
            "start": f"{period.start:%Y%m%d}", "end": f"{period.end:%Y%m%d}"})
        found = self._daily(daily, site)
        clim = get_json(f"{API}/climatology/point", timeout=90, params={
            "parameters": ",".join(CLIMATE), "community": "AG", "format": "JSON",
            "longitude": area.lon, "latitude": area.lat})
        found += self._climate(clim, site)
        if not found:
            raise NoData("NASA POWER returned only fill values (period not published?)")

    def _daily(self, response, site):
        v = {p: daily_values(response, p) for p in DAILY}
        if not v["T2M"]:
            return 0
        w, src = Weather(), self.name
        site.weather_by_source[self.name] = w
        mean = lambda xs: sum(xs) / len(xs)                      # noqa: E731
        w.air_temperature = Measurement(mean(v["T2M"]), "°C", src)
        if v["T2M_MIN"]:
            w.air_temperature_min = Measurement(min(v["T2M_MIN"]), "°C", src)
            w.frost_days = Measurement(sum(t <= 0 for t in v["T2M_MIN"]), "days", src,
                                       "daily minimum <= 0 °C")
        if v["T2M_MAX"]:
            w.air_temperature_max = Measurement(max(v["T2M_MAX"]), "°C", src)
            w.heat_days = Measurement(sum(t >= HEAT_DAY_C for t in v["T2M_MAX"]), "days",
                                      src, f"daily maximum >= {HEAT_DAY_C:g} °C")
        if v["T2MDEW"]:
            w.dewpoint = Measurement(mean(v["T2MDEW"]), "°C", src)
        if v["RH2M"]:
            w.relative_humidity = Measurement(mean(v["RH2M"]), "%", src)
        if v["PRECTOTCORR"]:
            w.precipitation = Measurement(sum(v["PRECTOTCORR"]), "mm", src,
                                          f"total of {len(v['PRECTOTCORR'])} day(s)")
            w.max_daily_precipitation = Measurement(max(v["PRECTOTCORR"]), "mm", src)
        if v["ALLSKY_SFC_SW_DWN"]:
            w.solar_radiation = Measurement(mean(v["ALLSKY_SFC_SW_DWN"]), "MJ/m²/day", src,
                                            "mean daily irradiation")
        if v["WS2M"]:
            w.wind_speed = Measurement(mean(v["WS2M"]), "m/s", src)
        if v["GWETTOP"]:
            site.soil.moisture["0-5cm POWER wetness"] = Measurement(
                mean(v["GWETTOP"]) * 100, "% of saturation", src)
        if v["GWETROOT"]:
            site.soil.moisture["0-100cm POWER wetness"] = Measurement(
                mean(v["GWETROOT"]) * 100, "% of saturation", src)
        if v["TS"]:
            site.soil.temperature["surface POWER"] = Measurement(mean(v["TS"]), "°C", src,
                                                                 "earth skin temperature")
        return 1

    def _climate(self, response, site):
        params = response.get("properties", {}).get("parameter", {})
        if not params:
            return 0
        years = ""
        for message in response.get("messages", []):
            if "(" in message and "-" in message:
                years = message[message.rfind("(") + 1:message.rfind(")")]
        c, src = site.climate, self.name
        c.years = years
        fill = response.get("header", {}).get("fill_value", -999.0)
        for param, (attr, unit) in CLIMATE_FIELDS.items():
            note = "monthly extreme" if attr.startswith("temperature_extreme") else ""
            getattr(c, attr).update({m: Measurement(val, unit, src, note)
                                     for m, val in params.get(param, {}).items()
                                     if val is not None and val != fill})
        return 1
