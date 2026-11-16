"""Light warnings about the coming days, from the forecast: big temperature
changes, rain, frost, heat, wind, strong sun. Short tips, not advice: the
details are in Analyze.
"""

from fieldshift.status.models import LEVEL_ALERT, LEVEL_WATCH, StatusAlert, num

# thresholds
TEMP_SWING_C = 8.0            # change of the maximum from one day to the next
RAIN_MM = 10.0
FROST_C = 2.0
HEAT_C = 32.0
WIND_KMH = 40.0
UV_HIGH = 9.0


# (tuple days)
# the first warning of each kind over the forecast days
# (api.forecast.DayForecast, today first)
def forecast_alerts(days):
    alerts, seen = [], set()

    def add(kind, day, key, params, level=LEVEL_WATCH):
        if kind not in seen:
            seen.add(kind)
            alerts.append(StatusAlert(key, params, level, day.date))
    for before, day in zip((None,) + tuple(days[:-1]), days):
        if before is not None and abs(day.tmax - before.tmax) >= TEMP_SWING_C:
            add("swing", day, "status.alert.temp_swing",
                {"before": num(before.tmax), "after": num(day.tmax)})
        if day.rain_mm >= RAIN_MM:
            add("rain", day, "status.alert.rain", {"mm": num(day.rain_mm)},
                LEVEL_ALERT if day.rain_mm >= 3 * RAIN_MM else LEVEL_WATCH)
        if day.tmin <= FROST_C:
            add("frost", day, "status.alert.frost", {"temp": num(day.tmin)},
                LEVEL_ALERT if day.tmin <= 0 else LEVEL_WATCH)
        if day.tmax >= HEAT_C:
            add("heat", day, "status.alert.heat", {"temp": num(day.tmax)})
        if day.wind_kmh is not None and day.wind_kmh >= WIND_KMH:
            add("wind", day, "status.alert.wind", {"kmh": num(day.wind_kmh)})
        if day.uv is not None and day.uv >= UV_HIGH:
            add("uv", day, "status.alert.uv", {"uv": num(day.uv)})
    return sorted(alerts, key=lambda a: a.date)
