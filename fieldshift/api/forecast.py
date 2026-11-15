"""Weather now and for the next 7 days at a point, from Open-Meteo.

    from fieldshift.api.forecast import get_forecast
    forecast = get_forecast(lon=-71.02, lat=-33.73)
    forecast.temperature          # °C now
    forecast.days[0].tmin         # °C, today

Open-Meteo (https://open-meteo.com) needs no key and is free for
non-commercial use; its data are CC BY 4.0, so ATTRIBUTION must be shown
wherever the forecast is shown. It complements the NASA sources of
fieldshift.api (which describe the past) with the days ahead. Standalone on
purpose: it is not a Provider because a forecast does not fit SiteData.
"""

import threading
from dataclasses import dataclass

from fieldshift.api.providers.base import get_json

URL = "https://api.open-meteo.com/v1/forecast"
# credit required by the CC BY 4.0 licence of the data
ATTRIBUTION = "Open-Meteo.com (CC BY 4.0)"
# days of forecast asked for
DAYS = 7
# most days the service forecasts
MAX_DAYS = 16
# a frost is forecast when the daily minimum is at or below this (°C)
FROST_C = 0.0
# results are reused for points in the same cell of this size (degrees,
# about 10 km: the resolution of the forecast models)
CACHE_CELL_DEG = 0.1

# kinds of weather the UI draws an icon for
SKY_CLEAR, SKY_PARTLY, SKY_CLOUDY, SKY_FOG = "clear", "partly", "cloudy", "fog"
SKY_RAIN, SKY_SNOW, SKY_STORM = "rain", "snow", "storm"

_cache = {}
_cache_lock = threading.Lock()


# forecast of one day: date "YYYY-MM-DD", min / max °C, rain mm, sky kind;
# and, when the service gives them, max wind km/h, mean air humidity %,
# sun MJ/m² and chance of rain %
@dataclass(frozen=True)
class DayForecast:
    date: str
    tmin: float
    tmax: float
    rain_mm: float
    sky: str
    wind_kmh: float = None
    humidity: float = None
    radiation: float = None
    rain_chance: float = None
    uv: float = None                     # max UV index
    et0: float = None                    # FAO reference evapotranspiration, mm


# forecast of one hour: time "YYYY-MM-DDTHH:MM", °C, sky kind, chance of rain
# %, wind km/h, top-soil (0-1 cm) water % vol and surface soil °C (None when
# the service does not give them)
@dataclass(frozen=True)
class HourForecast:
    time: str
    temp: float
    sky: str
    rain_chance: float = None
    wind_kmh: float = None
    soil_moisture: float = None
    soil_temp: float = None


# weather at a point: now (temperature °C, wind km/h, sky kind, humidity %,
# time "YYYY-MM-DDTHH:MM" in the place's time zone), the model's ground
# elevation (m), the next days (today first) and the hours of those days
@dataclass(frozen=True)
class Forecast:
    lon: float
    lat: float
    elevation: float
    temperature: float
    wind_kmh: float
    sky: str
    days: tuple
    humidity: float = None
    now: str = ""
    hours: tuple = ()

    # (str date = None)
    # the hours of a day ("YYYY-MM-DD", default today: the first day)
    def hours_of(self, date=None):
        date = date or (self.days[0].date if self.days else "")
        return [h for h in self.hours if h.time.startswith(date)]

    # ()
    # the hour the current time falls in, or None
    def current_hour(self):
        key = self.now[:13]
        return next((h for h in self.hours if h.time[:13] == key), None)

    # ()
    # the days whose minimum is at or below FROST_C
    def frost_days(self):
        return [d for d in self.days if d.tmin <= FROST_C]

    # ()
    # rain of all the days together, mm
    def total_rain_mm(self):
        return sum(d.rain_mm for d in self.days)


# (int code)
# sky kind (SKY_*) of a WMO weather code
def sky_of(code):
    if code == 0:
        return SKY_CLEAR
    if code in (1, 2):
        return SKY_PARTLY
    if code == 3:
        return SKY_CLOUDY
    if code in (45, 48):
        return SKY_FOG
    if code in (71, 73, 75, 77, 85, 86):
        return SKY_SNOW
    if code >= 95:
        return SKY_STORM
    return SKY_RAIN                       # drizzle, rain, showers (51-67, 80-82)


# (float lon, float lat)
# the cache cell of a point: points in one cell share a forecast
def cell_of(lon, lat):
    return (round(lon / CACHE_CELL_DEG), round(lat / CACHE_CELL_DEG))


# (dict response, float lon, float lat)
# Forecast from an Open-Meteo JSON answer; raises KeyError / TypeError /
# ValueError when the answer is not as expected
def parse_forecast(response, lon, lat):
    current, daily = response["current"], response["daily"]

    def extra(table, name, scale=1.0):     # optional values (None when missing)
        values = table.get(name) or []
        return ([None if v is None else float(v) * scale for v in values]
                + [None] * len(table.get("time", [])))
    days = tuple(
        DayForecast(date, float(tmin), float(tmax), float(rain or 0.0), sky_of(int(code)),
                    wind, humidity, sun, chance, uv, et0)
        for date, tmin, tmax, rain, code, wind, humidity, sun, chance, uv, et0 in zip(
            daily["time"], daily["temperature_2m_min"], daily["temperature_2m_max"],
            daily["precipitation_sum"], daily["weather_code"],
            extra(daily, "wind_speed_10m_max"), extra(daily, "relative_humidity_2m_mean"),
            extra(daily, "shortwave_radiation_sum"),
            extra(daily, "precipitation_probability_max"), extra(daily, "uv_index_max"),
            extra(daily, "et0_fao_evapotranspiration")))
    if not days:
        raise ValueError("forecast without days")
    hourly = response.get("hourly") or {}
    hours = tuple(
        HourForecast(time, float(temp), sky_of(int(code)), chance, wind, soil, soil_t)
        for time, temp, code, chance, wind, soil, soil_t in zip(
            hourly.get("time", []), hourly.get("temperature_2m", []),
            hourly.get("weather_code", []), extra(hourly, "precipitation_probability"),
            extra(hourly, "wind_speed_10m"), extra(hourly, "soil_moisture_0_to_1cm", 100.0),
            extra(hourly, "soil_temperature_0cm"))
        if temp is not None and code is not None)
    humidity = current.get("relative_humidity_2m")
    return Forecast(lon, lat, float(response.get("elevation") or 0.0),
                    float(current["temperature_2m"]), float(current["wind_speed_10m"]),
                    sky_of(int(current["weather_code"])), days,
                    None if humidity is None else float(humidity),
                    str(current.get("time") or ""), hours)


# (float lon, float lat, float timeout = 10, int days = DAYS)
# the forecast for a point and the next days (at most MAX_DAYS; cached per
# cell); raises when the service fails
def get_forecast(lon, lat, timeout=10, days=DAYS):
    key = (cell_of(lon, lat), days)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    response = get_json(URL, params={
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
        "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m,"
                  "soil_moisture_0_to_1cm,soil_temperature_0cm",
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code,"
                 "wind_speed_10m_max,relative_humidity_2m_mean,shortwave_radiation_sum,"
                 "precipitation_probability_max,uv_index_max,et0_fao_evapotranspiration",
        "forecast_days": min(days, MAX_DAYS), "timezone": "auto"}, timeout=timeout)
    forecast = parse_forecast(response, lon, lat)
    with _cache_lock:
        _cache[key] = forecast
    return forecast


# ()
# forgets the cached forecasts (tests, or to force a new download)
def clear_cache():
    with _cache_lock:
        _cache.clear()
