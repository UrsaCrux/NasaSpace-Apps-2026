"""Trends of a field: how it behaved over the last 12 months, against the
year before and the long-term normal. See docs/status.md.

    from fieldshift.trends import trends_report
    report = trends_report(field)
"""

from fieldshift.trends.models import (  # noqa: F401
    AGG_MEAN, AGG_SUM, Milestone, SeasonRow, TrendRow, TrendSection, TrendsReport)


# (Field field)
# the TrendsReport of the field, from the satellite sources. slow: call it
# outside the UI thread. offline, or when NASA POWER fails, example numbers
# (report.example is True, report.notice_key says why)
def trends_report(field):
    import os
    from dataclasses import replace
    from fieldshift.status import OFFLINE_ENV, crop_of
    from fieldshift.trends.example import example_report
    crop = crop_of(field)
    if os.environ.get(OFFLINE_ENV) == "1":
        return replace(example_report(field, crop), notice_key="status.offline")
    try:
        from fieldshift.trends.live import live_report
        return live_report(field, crop)
    except Exception:
        return replace(example_report(field, crop), notice_key="status.no_connection")
