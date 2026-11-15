"""The Status report of a field from the real sources: NASA POWER daily
weather and top-soil wetness, MODIS NDVI, the soil values stored with the
field (SoilGrids or typed by the farmer) and the Open-Meteo 7-day forecast.
The panel shows the "today" tiles; the rest (sections, warnings) is kept in
the report for later views.

A source that fails only leaves its rows out (its name goes to
report.missing); when NASA POWER fails the whole report fails.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fieldshift.analysis.models import TextureFigure
from fieldshift.status import rules, sources
from fieldshift.status.models import (
    CHART_BARS, StatusReport, StatusRow, StatusSection, SummaryTile)

# extra days asked to NASA POWER (its newest days are published ~3 days late)
POWER_LAG_DAYS = 7
# MODIS composites come every 16 days, ~1 month late: look this far back
NDVI_LOOKBACK_DAYS = 80
# stored soil values shown as fixed rows: (data key, row key, unit, decimals)
SOIL_FIXED = (("nitrogen", "nitrogen", "g/kg", 2), ("ph", "ph", "", 1),
              ("organic_carbon", "organic_carbon", "g/kg", 1), ("cec", "cec", "cmol/kg", 1))


def _centroid(field):
    lon = sum(v[0] for v in field.vertices) / len(field.vertices)
    lat = sum(v[1] for v in field.vertices) / len(field.vertices)
    return lon, lat


def _last(pairs, days):
    return pairs[-days:] if pairs else []


def _row(key, unit, pairs, decimals=1, source="NASA POWER", **options):
    return StatusRow(key, f"status.var.{key}", unit, tuple(d for d, _ in pairs),
                     tuple(round(v, decimals) for _, v in pairs), source=source,
                     decimals=decimals, **options)


def _weather_series(daily, days):
    def pick(name, scale=1.0):
        return [(d, v * scale) for d, v in _last(daily.get(name, []), days)]
    series = {"temp_max": pick("T2M_MAX"), "temp_min": pick("T2M_MIN"),
              "rain": pick("PRECTOTCORR"), "humidity": pick("RH2M"),
              "radiation": pick("ALLSKY_SFC_SW_DWN"), "wind": pick("WS2M", 3.6),
              "soil_moisture": pick("GWETTOP", 100.0), "soil_temp": pick("TS")}
    tmean = dict(_last(daily.get("T2M", []), days))
    series["et0"] = [(d, sources.et0(tmean[d], r)) for d, r in series["radiation"]
                     if d in tmean]
    return series


# (Field field, int days, callable forecast = None)
# the StatusReport of the field for the last days from the real sources.
# forecast(lon, lat) -> Forecast (default: Open-Meteo); raises when NASA
# POWER does not answer
def live_report(field, days, forecast=None, crop=None):
    from fieldshift.api import forecast as forecast_api
    lon, lat = _centroid(field)
    today = sources.today()
    start = today - timedelta(days=days + POWER_LAG_DAYS)
    missing = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        daily_job = pool.submit(sources.power_daily, lon, lat, start, today)
        ndvi_job = pool.submit(sources.modis_ndvi, lon, lat,
                               today - timedelta(days=max(days, NDVI_LOOKBACK_DAYS)), today)
        forecast_job = pool.submit(forecast or forecast_api.get_forecast, lon, lat)
        daily = daily_job.result()                       # raises: no report
        try:
            ndvi = ndvi_job.result()
        except Exception:
            ndvi, _ = [], missing.append("MODIS")
        try:
            coming = forecast_job.result()
        except Exception:
            coming, _ = None, missing.append("Open-Meteo")
    series = _weather_series(daily, days)
    if not series["temp_max"]:
        raise ValueError("NASA POWER returned no values")
    ndvi = ndvi[-4:]
    data = field.data or {}
    soil_values = {}
    for key, _, _, _ in SOIL_FIXED:
        item = data.get(key) or {}
        if item.get("value") is not None:              # stored with the field
            soil_values[key] = (item["value"], item.get("source"))

    values = {k: [v for _, v in pairs] for k, pairs in series.items()}
    values["ndvi"] = [v for _, v in ndvi]
    if "nitrogen" in soil_values:
        values["nitrogen"] = [soil_values["nitrogen"][0]]
    levels, observed = rules.observed(values)

    def row(key, unit, pairs, decimals=1, **options):
        return _row(key, unit, pairs, decimals, level=levels.get(key, "ok"), **options)

    weather = StatusSection("weather", "status.section.weather", "🌤️", tuple(r for r in (
        row("temp_max", "°C", series["temp_max"]),
        row("temp_min", "°C", series["temp_min"]),
        row("rain", "mm", series["rain"], chart=CHART_BARS),
        row("humidity", "%", series["humidity"], 0),
        row("radiation", "MJ/m²", series["radiation"]),
        row("wind", "km/h", series["wind"], 0),
        row("et0", "mm", series["et0"], source="NASA POWER (Hargreaves)"),
    ) if r.values), tuple(a for a in observed if a.text_key in _WEATHER_ALERTS))

    growth_rows = (row("ndvi", "", ndvi, 2, source="MODIS"),) if ndvi else ()
    note_params = {"crop": crop or "—",
                   "date": ndvi[-1][0] if ndvi else "—"}
    growth = StatusSection("growth", "status.section.growth", "🌱", growth_rows,
                           tuple(a for a in observed if a.text_key == "status.alert.ndvi_drop"),
                           note_key="status.growth_note", note_params=note_params)

    soil_rows = [row("soil_moisture", "%", series["soil_moisture"]),
                 row("soil_temp", "°C", series["soil_temp"])]
    for key, row_key, unit, decimals in SOIL_FIXED:
        if key in soil_values:
            value, source = soil_values[key]
            soil_rows.append(row(row_key, unit, [(series["temp_max"][-1][0], value)], decimals,
                                 fixed=True, source="status.source.farmer"
                                 if source == "user" else "SoilGrids"))
    texture_item = data.get("soil_texture") or {}
    texture = (TextureFigure(texture=texture_item["value"])
               if texture_item.get("value") else None)
    soil = StatusSection("soil", "status.section.soil", "🟫",
                         tuple(r for r in soil_rows if r.values),
                         tuple(a for a in observed if a.text_key in _SOIL_ALERTS),
                         texture=texture)

    upcoming = rules.upcoming(coming) if coming is not None else []
    # forecast warnings are kept with the weather section
    weather = StatusSection(**{**weather.__dict__, "alerts": weather.alerts + tuple(upcoming)})

    by_key = {r.key: r for s in (weather, growth, soil) for r in s.rows}
    summary = tuple(SummaryTile(section, by_key[key], icon) for section, key, icon in (
        ("weather", "temp_max", "🌡️"), ("weather", "rain", "🌧️"),
        ("weather", "humidity", "💧"), ("weather", "radiation", "☀️"),
        ("growth", "ndvi", "🌿"), ("soil", "soil_moisture", "🟫")) if key in by_key)
    return StatusReport(field.name, days, series["temp_max"][-1][0], (weather, growth, soil),
                        summary, example=False, missing=tuple(missing),
                        forecast=tuple(coming.days) if coming is not None else ())


_WEATHER_ALERTS = ("status.alert.heavy_rain", "status.alert.heat", "status.alert.frost",
                   "status.alert.radiation")
_SOIL_ALERTS = ("status.alert.dry_soil", "status.alert.low_nitrogen")
