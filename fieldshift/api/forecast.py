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


# forecast of one day: date "YYYY-MM-DD", min / max °C, rain mm, sky kind
@dataclass(frozen=True)
class DayForecast:
    date: str
    tmin: float
    tmax: float
    rain_mm: float
    sky: str


# weather at a point: now (temperature °C, wind km/h, sky kind), the model's
# ground elevation (m) and the next days, today first
@dataclass(frozen=True)
class Forecast:
    lon: float
    lat: float
    elevation: float
    temperature: float
    wind_kmh: float
    sky: str
    days: tuple

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
    days = tuple(
        DayForecast(date, float(tmin), float(tmax), float(rain or 0.0), sky_of(int(code)))
        for date, tmin, tmax, rain, code in zip(
            daily["time"], daily["temperature_2m_min"], daily["temperature_2m_max"],
            daily["precipitation_sum"], daily["weather_code"]))
    if not days:
        raise ValueError("forecast without days")
    return Forecast(lon, lat, float(response.get("elevation") or 0.0),
                    float(current["temperature_2m"]), float(current["wind_speed_10m"]),
                    sky_of(int(current["weather_code"])), days)


# (float lon, float lat, float timeout = 10)
# the forecast for a point (cached per cell); raises when the service fails
def get_forecast(lon, lat, timeout=10):
    cell = cell_of(lon, lat)
    with _cache_lock:
        if cell in _cache:
            return _cache[cell]
    response = get_json(URL, params={
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_min,temperature_2m_max,precipitation_sum,weather_code",
        "forecast_days": DAYS, "timezone": "auto"}, timeout=timeout)
    forecast = parse_forecast(response, lon, lat)
    with _cache_lock:
        _cache[cell] = forecast
    return forecast


# ()
# forgets the cached forecasts (tests, or to force a new download)
def clear_cache():
    with _cache_lock:
        _cache.clear()
