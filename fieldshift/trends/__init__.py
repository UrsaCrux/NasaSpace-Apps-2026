"""Trends of a field: how it behaved over the last 12 months, against the
year before and the long-term normal. See docs/status.md.

    from fieldshift.trends import trends_report
    report = trends_report(field)
"""

from fieldshift.trends.models import (  # noqa: F401
    AGG_MEAN, AGG_SUM, Milestone, SeasonRow, TrendRow, TrendSection, TrendsReport)


# (Field field)
# the TrendsReport of the field, from the satellite sources. slow: call it
# outside the UI thread. raises api.errors.DataError when NASA POWER cannot
# be downloaded; other sources that fail are listed in report.missing
def trends_report(field):
    from fieldshift.status import crop_of, offline_mode
    crop = crop_of(field)
    if offline_mode() == "example":
        from fieldshift.trends.example import example_report
        return example_report(field, crop)
    from fieldshift.trends.live import live_report
    return live_report(field, crop)
