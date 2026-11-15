"""Warnings of the Status panel from the observed series and the 7-day
forecast. Simple thresholds, the same for every crop for now (crop- and
stage-specific rules come with the farmer's records).
"""

from fieldshift.i18n import tr
from fieldshift.status.models import LEVEL_ALERT, LEVEL_WATCH, StatusAlert

# thresholds
HEAVY_RAIN_MM = 20.0          # one day
STRONG_SUN_MJ = 25.0          # MJ/m² in one day
HEAT_C = 35.0
FROST_C = 0.0
DRY_SOIL_PCT = 30.0           # % of saturation, top soil
LOW_SOIL_PCT = 45.0
NDVI_DROP_PCT = 10.0
LOW_NITROGEN = 1.0            # g/kg


# (int days)
# "Tomorrow" / "In 3 days" in the current language
def when(days):
    return tr("status.when.tomorrow") if days == 1 else tr("status.when.in_days", days=days)


# (dict series)
# {row key: level} and the observed alerts, from {row key: [values]} of the
# period (any key may be missing)
def observed(series):
    levels, alerts = {}, []
    rain = series.get("rain")
    if rain and max(rain) >= HEAVY_RAIN_MM:
        levels["rain"] = LEVEL_WATCH
        alerts.append(StatusAlert("status.alert.heavy_rain", {"mm": f"{max(rain):.0f}"},
                                  LEVEL_WATCH, suggestion=True))
    tmax = series.get("temp_max")
    if tmax and max(tmax) >= HEAT_C:
        levels["temp_max"] = LEVEL_WATCH
        alerts.append(StatusAlert("status.alert.heat", {"temp": f"{max(tmax):.0f}"},
                                  LEVEL_WATCH, suggestion=True))
    tmin = series.get("temp_min")
    if tmin and min(tmin) <= FROST_C:
        levels["temp_min"] = LEVEL_ALERT
        alerts.append(StatusAlert("status.alert.frost", {"temp": f"{min(tmin):.0f}",
                                                         "count": sum(t <= FROST_C for t in tmin)},
                                  LEVEL_ALERT, suggestion=True))
    sun = series.get("radiation")
    if sun and sun[-1] >= STRONG_SUN_MJ:
        levels["radiation"] = LEVEL_WATCH
        alerts.append(StatusAlert("status.alert.radiation", {"value": f"{sun[-1]:.0f}"},
                                  LEVEL_WATCH, suggestion=True))
    soil = series.get("soil_moisture")
    if soil and soil[-1] < LOW_SOIL_PCT:
        level = LEVEL_ALERT if soil[-1] < DRY_SOIL_PCT else LEVEL_WATCH
        levels["soil_moisture"] = level
        alerts.append(StatusAlert("status.alert.dry_soil", {"value": f"{soil[-1]:.0f}"},
                                  level, suggestion=True))
    ndvi = series.get("ndvi")
    if ndvi and len(ndvi) > 1 and ndvi[-2] > 0:
        drop = (ndvi[-2] - ndvi[-1]) / ndvi[-2] * 100
        if drop >= NDVI_DROP_PCT:
            levels["ndvi"] = LEVEL_WATCH
            alerts.append(StatusAlert("status.alert.ndvi_drop", {"pct": f"{drop:.0f}"},
                                      LEVEL_WATCH, suggestion=True))
    nitrogen = series.get("nitrogen")
    if nitrogen and nitrogen[-1] < LOW_NITROGEN:
        levels["nitrogen"] = LEVEL_WATCH
        alerts.append(StatusAlert("status.alert.low_nitrogen", {"value": f"{nitrogen[-1]:.2f}"},
                                  LEVEL_WATCH, suggestion=True))
    return levels, alerts


# (Forecast forecast)
# alerts about the next days (the first of each kind), from
# fieldshift.api.forecast.Forecast
def upcoming(forecast):
    alerts = []
    days = list(forecast.days[1:])               # days[0] is today
    for n, day in enumerate(days, 1):
        if day.rain_mm >= HEAVY_RAIN_MM * 0.75:
            level = LEVEL_ALERT if day.rain_mm >= 30 else LEVEL_WATCH
            alerts.append(StatusAlert("status.alert.rain_upcoming",
                                      {"when": when(n), "mm": f"{day.rain_mm:.0f}"},
                                      level, upcoming=True, suggestion=True, date=day.date))
            break
    for n, day in enumerate(days, 1):
        if day.tmin <= FROST_C:
            alerts.append(StatusAlert("status.alert.frost_upcoming",
                                      {"when": when(n), "temp": f"{day.tmin:.0f}"},
                                      LEVEL_ALERT, upcoming=True, suggestion=True,
                                      date=day.date))
            break
    for n, day in enumerate(days, 1):
        if day.tmax >= HEAT_C:
            alerts.append(StatusAlert("status.alert.heat_upcoming",
                                      {"when": when(n), "temp": f"{day.tmax:.0f}"},
                                      LEVEL_WATCH, upcoming=True, suggestion=True,
                                      date=day.date))
            break
    return alerts


