"""Daily weather for a crop simulation: what happened, what is forecast,
and the zone's climate for the rest of the season.

For a period [start, end] the series is assembled from, in order:

1. observed days (up to today): Open-Meteo (archive + the forecast API's
   past days); when Open-Meteo fails (or is rate-limited), NASA POWER;
2. forecast days: the Open-Meteo forecast, up to 16 days ahead;
3. climate: any day still missing (the season goes on after the forecast)
   takes the weather of the same calendar day one year earlier (two, three...
   if needed) from the days above: a real, recent year of the zone.

Every day keeps where it came from (source: observed / forecast / climate)
so the result can say how much of the season is forecast or climate.
Values are converted to what PCSE expects: IRRAD J/m²/day, RAIN cm/day,
VAP hPa, WIND m/s at 2 m, TMIN / TMAX °C.
"""

import datetime as dt
import math
from dataclasses import dataclass, field

from fieldshift.api.providers.base import get_json

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
POWER_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"
OPEN_METEO_DAILY = ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
                    "shortwave_radiation_sum,wind_speed_10m_mean,dew_point_2m_mean")
POWER_PARAMETERS = "T2M_MAX,T2M_MIN,ALLSKY_SFC_SW_DWN,PRECTOTCORR,WS2M,T2MDEW"
# days of past weather the Open-Meteo forecast API returns, and days ahead
PAST_DAYS, FORECAST_DAYS = 92, 16
# wind at 10 m to wind at 2 m (FAO-56 logarithmic profile)
WIND_10M_TO_2M = 4.87 / math.log(67.8 * 10 - 5.42)
# Angstrom coefficients for the reference evapotranspiration (as PCSE)
ANGSTROM_A, ANGSTROM_B = 0.29, 0.49

SOURCE_OBSERVED, SOURCE_FORECAST, SOURCE_CLIMATE = "observed", "forecast", "climate"


# (float tdew)
# actual vapour pressure (hPa) from the dew point (°C)
def vapour_pressure(tdew):
    return 6.10588 * math.exp(17.32491 * tdew / (tdew + 238.102))


# one day of weather, in PCSE units
@dataclass
class Day:
    date: dt.date
    tmin: float
    tmax: float
    irrad: float        # J/m²/day
    rain: float         # cm/day
    vap: float          # hPa
    wind: float         # m/s at 2 m
    source: str = SOURCE_OBSERVED


# the assembled series: days by date, where each came from, and the
# provider names used ("Open-Meteo", "NASA POWER")
@dataclass
class WeatherSeries:
    days: dict
    providers: list = field(default_factory=list)
    elevation: float = 0.0

    # ()
    # {source: number of days}
    def counts(self):
        result = {}
        for day in self.days.values():
            result[day.source] = result.get(day.source, 0) + 1
        return result


# (dict response, dt.date today)
# Days of an Open-Meteo daily answer (forecast or archive); days from today
# on are marked "forecast"; incomplete days are skipped
def parse_open_meteo(response, today):
    daily = response["daily"]
    days = []
    for i, text in enumerate(daily["time"]):
        values = [daily[k][i] for k in ("temperature_2m_min", "temperature_2m_max",
                                        "shortwave_radiation_sum", "precipitation_sum",
                                        "dew_point_2m_mean", "wind_speed_10m_mean")]
        if any(v is None for v in values):
            continue
        tmin, tmax, rad, rain, tdew, wind10 = (float(v) for v in values)
        date = dt.date.fromisoformat(text)
        days.append(Day(date, tmin, tmax, rad * 1e6, rain / 10.0, vapour_pressure(tdew),
                        wind10 * WIND_10M_TO_2M,
                        SOURCE_FORECAST if date >= today else SOURCE_OBSERVED))
    return days


# (dict response)
# observed Days of a NASA POWER daily answer (fill values skipped)
def parse_power(response):
    fill = response.get("header", {}).get("fill_value", -999.0)
    p = response["properties"]["parameter"]
    days = []
    for key in sorted(p["T2M_MAX"]):
        values = [p[name].get(key) for name in ("T2M_MIN", "T2M_MAX", "ALLSKY_SFC_SW_DWN",
                                                "PRECTOTCORR", "T2MDEW", "WS2M")]
        if any(v is None or v == fill for v in values):
            continue
        tmin, tmax, rad, rain, tdew, wind = (float(v) for v in values)
        days.append(Day(dt.datetime.strptime(key, "%Y%m%d").date(), tmin, tmax, rad * 1e6,
                        rain / 10.0, vapour_pressure(tdew), wind))
    return days


# (float lat, float lon, dt.date start, dt.date today)
# (days, elevation) from Open-Meteo: archive up to PAST_DAYS ago, then the
# forecast API (recent days + FORECAST_DAYS ahead). Raises on failure
def fetch_open_meteo(lat, lon, start, today):
    params = {"latitude": round(lat, 4), "longitude": round(lon, 4), "daily": OPEN_METEO_DAILY,
              "wind_speed_unit": "ms", "timezone": "UTC"}
    forecast = get_json(OPEN_METEO_FORECAST, timeout=60, params={
        **params, "past_days": PAST_DAYS, "forecast_days": FORECAST_DAYS})
    days = parse_open_meteo(forecast, today)
    first_recent = today - dt.timedelta(days=PAST_DAYS)
    if start < first_recent:
        archive = get_json(OPEN_METEO_ARCHIVE, timeout=90, params={
            **params, "start_date": start.isoformat(),
            "end_date": (first_recent - dt.timedelta(days=1)).isoformat()})
        days = parse_open_meteo(archive, today) + days
    return days, float(forecast.get("elevation") or 0.0)


# (float lat, float lon, dt.date start, dt.date end)
# observed days from NASA POWER (no forecast). Raises on failure
def fetch_power(lat, lon, start, end):
    response = get_json(POWER_DAILY, timeout=120, params={
        "parameters": POWER_PARAMETERS, "community": "AG", "format": "JSON",
        "longitude": round(lon, 4), "latitude": round(lat, 4),
        "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}"})
    return parse_power(response)


# (float lat, float lon, dt.date start, dt.date end, dt.date today = None,
#  callable open_meteo = fetch_open_meteo, callable power = fetch_power)
# WeatherSeries covering every day of [start, end] (see the module text).
# History is fetched from a year before the earliest day needed, so the
# climate fill always has a recent year to copy from. Raises RuntimeError
# when no source answers
def build_weather(lat, lon, start, end, today=None, open_meteo=None, power=None):
    today = today or dt.date.today()
    open_meteo, power = open_meteo or fetch_open_meteo, power or fetch_power
    history_start = min(start, today) - dt.timedelta(days=400)
    known, providers, elevation, errors = {}, [], 0.0, []
    try:
        days, elevation = open_meteo(lat, lon, history_start, today)
        if days:
            providers.append("Open-Meteo")
            known.update((d.date, d) for d in days)
    except Exception as exc:
        errors.append(f"Open-Meteo: {exc}")
    if not known:
        try:
            days = power(lat, lon, history_start, today)
            if days:
                providers.append("NASA POWER")
                known.update((d.date, d) for d in days)
        except Exception as exc:
            errors.append(f"NASA POWER: {exc}")
    if not known:
        raise RuntimeError("no weather source answered: " + "; ".join(errors))

    series = {}
    day = start
    while day <= end:
        if day in known:
            series[day] = known[day]
        else:
            series[day] = _climate_day(day, known)
        day += dt.timedelta(days=1)
    return WeatherSeries(series, providers, elevation)


def _climate_day(day, known):
    for years in range(1, 6):
        try:
            source_day = day.replace(year=day.year - years)
        except ValueError:                           # 29 February
            source_day = day.replace(year=day.year - years, day=28)
        if source_day in known:
            d = known[source_day]
            return Day(day, d.tmin, d.tmax, d.irrad, d.rain, d.vap, d.wind, SOURCE_CLIMATE)
    nearest = min(known, key=lambda k: abs((k - day).days))   # last resort: closest day
    d = known[nearest]
    return Day(day, d.tmin, d.tmax, d.irrad, d.rain, d.vap, d.wind, SOURCE_CLIMATE)


# (WeatherSeries series, float lat, float lon)
# a PCSE WeatherDataProvider serving the series (with reference
# evapotranspiration computed as PCSE's own providers do)
def pcse_provider(series, lat, lon):
    from pcse.base import WeatherDataContainer, WeatherDataProvider
    from pcse.util import reference_ET

    class SeriesWeatherDataProvider(WeatherDataProvider):
        def __init__(self):
            super().__init__()
            self.description = ["Field Shift: " + ", ".join(series.providers)
                                + " (observed / forecast) + same days of past years"]
            for d in series.days.values():
                e0, es0, et0 = reference_ET(d.date, lat, series.elevation, d.tmin, d.tmax,
                                            d.irrad, d.vap, d.wind, ANGSTROM_A, ANGSTROM_B, "PM")
                wdc = WeatherDataContainer(
                    LAT=lat, LON=lon, ELEV=series.elevation, DAY=d.date, IRRAD=d.irrad,
                    TMIN=d.tmin, TMAX=d.tmax, VAP=d.vap, RAIN=d.rain, WIND=d.wind,
                    E0=e0 / 10.0, ES0=es0 / 10.0, ET0=et0 / 10.0)
                self._store_WeatherDataContainer(wdc, d.date)

    return SeriesWeatherDataProvider()
