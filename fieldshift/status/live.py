"""The Status report of a field from the real sources: the Open-Meteo
forecast (today, its hours and the next 16 days) and, apart because it is
slow, the MODIS NDVI follow-up of the crop.
"""

from datetime import timedelta

from fieldshift.status import rules, sources
from fieldshift.status.build import today_tiles
from fieldshift.status.models import FORECAST_DAYS, StatusReport, Tracking

# MODIS composites come every 16 days, ~1 month late: look this far back
NDVI_LOOKBACK_DAYS = 80


def _centroid(field):
    lon = sum(v[0] for v in field.vertices) / len(field.vertices)
    lat = sum(v[1] for v in field.vertices) / len(field.vertices)
    return lon, lat


# (Field field, callable forecast = None)
# today and the coming days of the field; forecast(lon, lat, days=) ->
# Forecast (default: Open-Meteo). raises when the forecast fails
def live_report(field, forecast=None):
    from fieldshift.api import forecast as forecast_api
    lon, lat = _centroid(field)
    coming = (forecast or forecast_api.get_forecast)(lon, lat, days=FORECAST_DAYS)
    return StatusReport(field.name, today_tiles(coming), coming,
                        tuple(rules.forecast_alerts(coming.days)))


# (Field field, str crop)
# the crop follow-up from the two newest NDVI images, or None when MODIS has
# none; raises when MODIS fails
def live_tracking(field, crop):
    lon, lat = _centroid(field)
    today = sources.today()
    images = sources.modis_ndvi(lon, lat, today - timedelta(days=NDVI_LOOKBACK_DAYS), today)
    if not images:
        return None
    date, ndvi = images[-1]
    previous_date, previous = images[-2] if len(images) > 1 else ("", None)
    return Tracking(crop, ndvi, date, previous, previous_date)
