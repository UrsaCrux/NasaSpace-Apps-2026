"""What to export and the downloading of it (no Qt: runs in a worker thread)."""

from dataclasses import dataclass, field as dataclass_field


# what the user chose to export. analyses: ids of fieldshift.analysis.ANALYSES
@dataclass(frozen=True)
class ExportOptions:
    geojson: bool = True
    records: bool = True
    status: bool = False
    trends: bool = False
    analyses: tuple = ()

    # ()
    # True when nothing has to be downloaded (fast)
    def offline_only(self):
        return not (self.status or self.trends or self.analyses)


# everything exported for one field: the reports, or the Exception that
# explains why one is missing (api.errors.DataError)
@dataclass
class FieldBundle:
    field: object
    status: object = None
    trends: object = None
    analyses: list = dataclass_field(default_factory=list)     # AnalysisResult


# (Field field, ExportOptions options, callable step = None, callable cancelled = None)
# downloads / computes the chosen reports of a field. step(text) is called
# before each part; cancelled() -> True stops early. never raises: a failed
# part keeps its exception
def collect(field, options, step=None, cancelled=None):
    from fieldshift.analysis import get_analysis
    bundle = FieldBundle(field)
    jobs = []
    if options.status:
        jobs.append(("status", lambda: _status(field)))
    if options.trends:
        jobs.append(("trends", lambda: _trends(field)))
    for analysis_id in options.analyses:
        jobs.append((analysis_id, lambda a=analysis_id: get_analysis(a).run(field)))
    for name, job in jobs:
        if cancelled is not None and cancelled():
            break
        if step is not None:
            step(name)
        try:
            value = job()
        except Exception as exc:
            value = exc
        if name == "status":
            bundle.status = value
        elif name == "trends":
            bundle.trends = value
        else:
            bundle.analyses.append(value)
    return bundle


def _status(field):
    from fieldshift.status import crop_tracking, status_report
    report = status_report(field)
    try:
        tracking = crop_tracking(field)
    except Exception as exc:
        tracking = exc
    return report, tracking


def _trends(field):
    from fieldshift.trends import trends_report
    return trends_report(field)
