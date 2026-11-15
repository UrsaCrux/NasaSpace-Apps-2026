"""Status of a field: how it is now (the last days, plus short warnings
about the next ones). See docs/status.md.

    from fieldshift.status import status_report
    report = status_report(field, days=7)
"""

from fieldshift.status.models import (  # noqa: F401
    CHART_BARS, CHART_LINE, LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH, PERIODS, StatusAlert,
    StatusReport, StatusRow, StatusSection, SummaryTile)


# (Field field, int days = 7)
# the StatusReport of the field for the last days (one of PERIODS). for now
# made-up example numbers (report.example is True)
def status_report(field, days=7):
    from fieldshift.status.example import example_report
    crop = (field.data or {}).get("crop") or {}
    name = crop.get("name")
    if not name and crop.get("value"):
        try:
            from fieldshift.crops import label
            name = label(crop["value"])
        except Exception:
            name = crop["value"]
    return example_report(field, days, crop=name)
