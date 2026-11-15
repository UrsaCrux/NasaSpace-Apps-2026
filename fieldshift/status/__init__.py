"""Status of a field: how it is now (the last days, plus short warnings
about the next ones). See docs/status.md.

    from fieldshift.status import status_report
    report = status_report(field, days=7)
"""

from fieldshift.status.models import (  # noqa: F401
    CHART_BARS, CHART_LINE, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH, PERIODS, StatusAlert,
    StatusReport, StatusRow, StatusSection, SummaryTile)


# when set to "1" nothing contacts the data services (tests): example data
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"


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


# (Field field, int days = 7)
# the StatusReport of the field for the last days (one of PERIODS), from the
# satellite sources. slow (seconds to a minute): call it outside the UI
# thread. offline, or when NASA POWER fails, made-up example numbers
# (report.example is True, report.notice_key says why)
def status_report(field, days=7):
    import os
    from dataclasses import replace
    from fieldshift.status.example import example_report
    crop = crop_of(field)
    if os.environ.get(OFFLINE_ENV) == "1":
        return replace(example_report(field, days, crop=crop), notice_key="status.offline")
    try:
        from fieldshift.status.live import live_report
        return live_report(field, days, crop=crop)
    except Exception:
        return replace(example_report(field, days, crop=crop), notice_key="status.no_connection")
