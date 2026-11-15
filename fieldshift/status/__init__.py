"""Status of a field: today and the coming days (forecast, light warnings)
and the follow-up of its crop. See docs/status.md. (The past is in
fieldshift.trends.)

    from fieldshift.status import status_report, crop_tracking
    report = status_report(field)
"""

from fieldshift.status.models import (  # noqa: F401
    CHART_BARS, CHART_LINE, FORECAST_DAYS, HORIZONS, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH,
    StatusAlert, StatusReport, TodayTile, Tracking)

# when set to "1" nothing contacts the data services: the reports fail with
# errors.OFFLINE (the tests also set EXAMPLE_ENV to get example numbers)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"
# when set to "1" (tests only) offline reports are made-up example numbers
EXAMPLE_ENV = "FIELDSHIFT_EXAMPLE_DATA"


# ()
# None when the services may be contacted; "example" (tests) or raises
# DataError(OFFLINE) when the app runs offline
def offline_mode():
    import os
    from fieldshift.api.errors import OFFLINE, DataError
    if os.environ.get(OFFLINE_ENV) != "1":
        return None
    if os.environ.get(EXAMPLE_ENV) == "1":
        return "example"
    raise DataError(OFFLINE)


# (Field field)
# name of the field's crop in the current language, or None
def crop_of(field):
    crop = (field.data or {}).get("crop") or {}
    name = crop.get("name")
    if not name and crop.get("value"):
        try:
            from fieldshift.crops import label
            name = label(crop["value"])
        except Exception:
            name = crop["value"]
    return name


# (Field field)
# the StatusReport of the field (today and the next FORECAST_DAYS days),
# with the farmer's measurements of today in place of the forecast's. a
# network call: run it outside the UI thread. raises api.errors.DataError
# (no connection, timeout, ...) when the forecast cannot be downloaded
def status_report(field):
    if offline_mode() == "example":
        from fieldshift.status.example import example_report
        return example_report(field)
    from fieldshift.status.live import live_report
    return live_report(field)


# (Field field)
# the crop follow-up (Tracking) of the field: NDVI images, sowing date and
# measured plant height. slow (MODIS, up to a minute): run it outside the UI
# thread. raises api.errors.DataError when MODIS fails
def crop_tracking(field):
    crop = crop_of(field)
    if offline_mode() == "example":
        from fieldshift.status.example import example_tracking
        return example_tracking(field, crop)
    from fieldshift.status.live import live_tracking
    return live_tracking(field, crop)
