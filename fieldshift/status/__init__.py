"""Status of a field: today and the coming days (forecast, light warnings)
and the follow-up of its crop. See docs/status.md. (The past is in
fieldshift.trends.)

    from fieldshift.status import status_report, crop_tracking
    report = status_report(field)
"""

from fieldshift.status.models import (  # noqa: F401
    CHART_BARS, CHART_LINE, FORECAST_DAYS, HORIZONS, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH,
    StatusAlert, StatusReport, TodayTile, Tracking)

# when set to "1" nothing contacts the data services (tests): example data
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"


def _offline():
    import os
    return os.environ.get(OFFLINE_ENV) == "1"


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
# the StatusReport of the field (today and the next FORECAST_DAYS days).
# a network call: run it outside the UI thread. offline, or when the
# forecast fails, made-up example numbers (report.example is True,
# report.notice_key says why)
def status_report(field):
    from dataclasses import replace
    from fieldshift.status.example import example_report
    if _offline():
        return replace(example_report(field), notice_key="status.offline")
    try:
        from fieldshift.status.live import live_report
        return live_report(field)
    except Exception:
        return replace(example_report(field), notice_key="status.no_connection")


# (Field field)
# the crop follow-up (Tracking) of the field, or None when there is no NDVI.
# slow (MODIS, up to a minute): run it outside the UI thread. raises when
# MODIS fails (offline: example)
def crop_tracking(field):
    crop = crop_of(field)
    if _offline():
        from fieldshift.status.example import example_tracking
        return example_tracking(field, crop)
    from fieldshift.status.live import live_tracking
    return live_tracking(field, crop)
