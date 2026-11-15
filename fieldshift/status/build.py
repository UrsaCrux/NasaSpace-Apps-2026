"""Today's tiles from a forecast (shared by the real and the example report),
with the farmer's measurements of today in place of the forecast's values.
"""

from dataclasses import replace

from fieldshift.fields.records import latest
from fieldshift.status.models import LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH, TodayTile
from fieldshift.status.rules import FROST_C, HEAT_C, RAIN_MM, UV_HIGH, WIND_KMH


# tile key -> record kind measured in the field
MEASURED_KINDS = {"soil_moisture": "soil_moisture", "soil_temp": "soil_temp"}


# (api.forecast.Forecast forecast, tuple records = ())
# the tiles of today: temperature, rain, humidity, wind, sun, water use and
# top soil; a tile with a measurement of today (records) shows it instead
def today_tiles(forecast, records=()):
    tiles = _forecast_tiles(forecast)
    today = forecast.days[0].date
    out = []
    for tile in tiles:
        record = latest(records, MEASURED_KINDS.get(tile.key, ""), today)
        if record is not None and record.value is not None:
            tile = replace(tile, value=record.value, measured=record.time[11:16],
                           note_key="status.tile.measured_note", note_params={})
        out.append(tile)
    return tuple(out)


def _forecast_tiles(forecast):
    day = forecast.days[0]
    hour = forecast.current_hour() or (forecast.hours[0] if forecast.hours else None)
    hot = day.tmax >= HEAT_C or day.tmin <= FROST_C
    return (
        TodayTile("temp", "🌡️", "status.tile.temp", forecast.temperature, "°C", 0,
                  "status.tile.temp_note", {"tmax": f"{day.tmax:.0f}", "tmin": f"{day.tmin:.0f}"},
                  LEVEL_WATCH if hot else LEVEL_OK),
        TodayTile("rain", "🌧️", "status.tile.rain", day.rain_mm, "mm", 1,
                  "status.tile.rain_note" if day.rain_chance is not None else "",
                  {"pct": f"{day.rain_chance or 0:.0f}"},
                  LEVEL_WATCH if day.rain_mm >= RAIN_MM else LEVEL_OK),
        TodayTile("humidity", "💧", "status.tile.humidity", forecast.humidity, "%", 0,
                  "status.tile.humidity_note" if day.humidity is not None else "",
                  {"pct": f"{day.humidity or 0:.0f}"}),
        TodayTile("wind", "💨", "status.tile.wind", forecast.wind_kmh, "km/h", 0,
                  "status.tile.wind_note" if day.wind_kmh is not None else "",
                  {"kmh": f"{day.wind_kmh or 0:.0f}"},
                  LEVEL_WATCH if (day.wind_kmh or 0) >= WIND_KMH else LEVEL_OK),
        TodayTile("sun", "☀️", "status.tile.sun", day.radiation, "MJ/m²", 1,
                  "status.tile.sun_note" if day.uv is not None else "",
                  {"uv": f"{day.uv or 0:.0f}"},
                  LEVEL_WATCH if (day.uv or 0) >= UV_HIGH else LEVEL_OK),
        TodayTile("et0", "💦", "status.tile.et0", day.et0, "mm", 1, "status.tile.et0_note"),
        TodayTile("soil_moisture", "🟫", "status.tile.soil_moisture",
                  hour.soil_moisture if hour else None, "%", 0, "status.tile.soil_note",
                  level=LEVEL_ALERT if hour and hour.soil_moisture is not None
                  and hour.soil_moisture < 10 else LEVEL_OK),
        TodayTile("soil_temp", "🌱", "status.tile.soil_temp",
                  hour.soil_temp if hour else None, "°C", 0, "status.tile.soil_note"),
    )
