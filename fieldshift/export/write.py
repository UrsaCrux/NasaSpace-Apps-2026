"""Writes an export ZIP: informe.pdf (readable report with charts), and per
field the GeoJSON, measurements CSV and each result as JSON / CSV / PNG.
Charts are drawn with the app's own widgets, so this runs in the UI thread.
"""

import csv
import io
import json
import re
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from html import escape

from fieldshift import __version__
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui

# size of the chart pictures, pixels
CHART_SIZE = (900, 340)
MAP_SIZE = (420, 360)


# (str name)
# a folder / file name safe on every system
def safe_name(name):
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .") or "field"


def _json(value):
    def default(obj):
        if is_dataclass(obj):
            return asdict(obj)
        return str(obj)
    return json.dumps(value if not is_dataclass(value) else asdict(value), default=default,
                      ensure_ascii=False, indent=2).encode("utf-8")


def _csv(header, rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _png(image):
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _grab(widget, size):
    widget.resize(*size)
    widget.ensurePolished()
    return widget.grab().toImage()


def _error(exc):
    from fieldshift.ui.field_panel import error_text
    return f"<p style='color:#8a1c13'>{escape(error_text(exc))}</p>"


def _table(header, rows):
    head = "".join(f"<th align='left'>{escape(str(h))}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>"
                   for row in rows)
    return (f"<table border='1' cellspacing='0' cellpadding='3' width='100%'>"
            f"<tr style='background:#e8efe8'>{head}</tr>{body}</table>")


# collects the files of the ZIP and the pictures of the report
class _Writer:

    def __init__(self):
        self.files = {}               # path in the zip -> bytes
        self.images = {}              # name in the report -> QImage
        self.html = []

    def image(self, folder, name, image):
        key = f"{folder}/{name}.png"
        self.files[key] = _png(image)
        self.images[key] = image
        self.html.append(f"<p><img src='{key}' width='640'></p>")

    # -- one field ----------------------------------------------------------

    def field(self, bundle, options):
        field = bundle.field
        folder = safe_name(field.name)
        self.html.append(f"<h1>{escape(field.name)}</h1><p>"
                         + escape(tr("export.field_line", area=f"{field.area_ha:.2f}",
                                     created=field.created[:10])) + "</p>")
        if options.geojson:
            from fieldshift.fields.store import to_feature
            self.files[f"{folder}/terreno.geojson"] = _json(
                {"type": "FeatureCollection", "features": [to_feature(field)]})
        if options.records:
            self._records(folder, field)
        if options.status:
            self._status(folder, bundle.status)
        if options.trends:
            self._trends(folder, bundle.trends)
        for result in bundle.analyses:
            self._analysis(folder, result, field)

    def _records(self, folder, field):
        from fieldshift.fields.records import KINDS
        rows = [(r.time.replace("T", " "), tr(f"records.kind.{r.kind}"),
                 "" if r.value is None else r.value, KINDS[r.kind][0],
                 tr(f"records.origin.{r.origin}"), r.crop, r.note) for r in field.records]
        header = [tr(f"records.col.{c}") for c in ("time", "kind", "value")] + [
            tr("export.unit"), tr("records.col.origin"), tr("records.col.crop"),
            tr("records.col.note")]
        self.files[f"{folder}/mediciones.csv"] = _csv(header, rows)
        self.html.append(f"<h2>{escape(tr('export.records'))}</h2>")
        self.html.append(_table(header[:6], [r[:6] for r in rows]) if rows
                         else f"<p>{escape(tr('export.no_records'))}</p>")

    def _status(self, folder, value):
        from fieldshift.ui.status_widgets import ForecastChart
        self.html.append(f"<h2>{escape(tr('modes.status'))}</h2>")
        if isinstance(value, Exception):
            self.html.append(_error(value))
            return
        report, tracking = value
        self.files[f"{folder}/status.json"] = _json(report)
        days = report.forecast.days
        self.files[f"{folder}/pronostico.csv"] = _csv(
            ["date", "tmin_c", "tmax_c", "rain_mm", "rain_chance_pct", "wind_kmh",
             "humidity_pct", "sun_mj_m2", "uv", "et0_mm"],
            [(d.date, d.tmin, d.tmax, d.rain_mm, d.rain_chance, d.wind_kmh, d.humidity,
              d.radiation, d.uv, d.et0) for d in days])
        tiles = [(tr(t.label_key), "—" if t.value is None else
                  f"{t.value:.{t.decimals}f} {t.unit}".strip()
                  + (f" ({tr('export.measured')} {t.measured})" if t.measured else ""))
                 for t in report.tiles]
        self.html.append(f"<h3>{escape(tr('status.today'))} · {days[0].date}</h3>")
        self.html.append(_table([tr("export.what"), tr("export.value")], tiles))
        self.html.append(f"<h3>{escape(tr('status.soon_title'))}</h3>")
        for variable in ("temp", "rain"):
            chart = ForecastChart(days[:14])
            chart.show_day(variable, 0)
            self.image(folder, f"pronostico_{variable}", _grab(chart, CHART_SIZE))
        if report.alerts:
            items = "".join(f"<li><b>{a.date}</b>: {escape(tr(a.text_key, **a.params))}</li>"
                            for a in report.alerts)
            self.html.append(f"<p><b>{escape(tr('status.tips_title'))}</b></p><ul>{items}</ul>")
        self.html.append(f"<h3>{escape(tr('status.tracking_title'))}</h3>")
        if isinstance(tracking, Exception):
            self.html.append(_error(tracking))
        elif tracking is not None:
            change = tracking.change_pct()
            self.html.append(f"<p>NDVI {tracking.ndvi:.2f} ({tracking.date})"
                             + (f", {change:+.0f}% vs {tracking.previous_date}"
                                if change is not None else "") + "</p>")

    def _trends(self, folder, report):
        from fieldshift.ui.trends_widgets import YearChart, long_month
        self.html.append(f"<h2>{escape(tr('modes.trends'))}</h2>")
        if isinstance(report, Exception):
            self.html.append(_error(report))
            return
        self.files[f"{folder}/trends.json"] = _json(report)
        rows = [r for s in report.sections for r in s.rows]
        header = ["month"] + [f"{r.key}{'_' + r.unit if r.unit else ''}" for r in rows]
        self.files[f"{folder}/trends.csv"] = _csv(header, [
            [m] + [r.values[i] for r in rows] for i, m in enumerate(report.months)])
        self.html.append(f"<p>{escape(long_month(report.months[0]))} – "
                         f"{escape(long_month(report.months[-1]))}</p>")
        for error in report.missing:
            self.html.append(_error(error))
        if report.milestones:
            self.html.append(_table([tr("trends.milestones"), tr("export.value")], [
                (tr(m.label_key), m.value + (f" · {long_month(m.month)}" if m.month else ""))
                for m in report.milestones]))
        for section in report.sections:
            if not section.rows:
                continue
            self.html.append(f"<h3>{escape(tr(section.title_key))}</h3>")
            self.html.append(_table(
                [tr("trends.col.variable"), tr("trends.col.year"), tr("trends.col.previous"),
                 tr("trends.col.normal")],
                [(tr(r.label_key) + (f" ({r.unit})" if r.unit else ""),
                  *("—" if v is None else f"{v:.{r.decimals}f}"
                    for v in (r.total(), r.previous_total(), r.normal_total())))
                 for r in section.rows]))
            for row in section.rows[:2]:
                chart = YearChart(row)
                self.image(folder, f"trends_{row.key}", _grab(chart, CHART_SIZE))

    def _analysis(self, folder, result, field):
        from fieldshift.analysis import get_analysis
        from fieldshift.ui.analysis_widgets import (
            FieldPreview, LineChart, figure_widget, localize, series_title)
        if isinstance(result, Exception):
            self.html.append(_error(result))
            return
        analysis = get_analysis(result.analysis_id)
        name = result.analysis_id
        self.html.append(f"<h2>{escape(tr(analysis.title_key))}</h2>")
        self.files[f"{folder}/analisis/{name}.json"] = _json(result)
        params = {k: localize(v) for k, v in result.summary_params.items()}
        self.html.append(f"<p><b>{escape(localize(tr(result.summary_key, **params)))}</b></p>")
        self.html.append(_table([tr("export.what"), tr("export.value")], [
            (tr(m.label_key), localize(m.value)) for m in result.metrics]))
        if result.series is not None:
            s = result.series
            self.files[f"{folder}/analisis/{name}.csv"] = _csv(
                ["date", f"value_{s.unit}" if s.unit else "value"], zip(s.dates, s.values))
            self.html.append(f"<p>{escape(series_title(s))}</p>")
            self.image(f"{folder}/analisis", f"{name}_grafico", _grab(LineChart(s), CHART_SIZE))
        if result.frames is not None:
            preview = FieldPreview(field.vertices, result.frames)
            preview.set_frame(len(result.frames.dates) - 1)
            self.image(f"{folder}/analisis", f"{name}_mapa", _grab(preview, MAP_SIZE))
        figure = figure_widget(result.figure) if result.figure is not None else None
        if figure is not None:
            self.image(f"{folder}/analisis", f"{name}_figura", _grab(figure, MAP_SIZE))
        order = {"high": 0, "medium": 1, "low": 2}
        ordered = sorted(result.recommendations, key=lambda r: order.get(r.priority, 1))

        def text(rec):
            return localize(tr(rec.text_key, **{k: localize(v) for k, v in rec.params.items()}))
        items = "".join(f"<li><b>{escape(tr('analysis.priority.' + r.priority))}</b>: "
                        f"{escape(text(r))}</li>" for r in ordered)
        self.html.append(f"<p><b>{escape(tr('analysis.recommendations'))}</b></p><ul>{items}</ul>")
        sources = ", ".join(f"{s.name} ({tr(s.variable_key)})" for s in result.sources)
        self.html.append(f"<p style='color:#555'>{escape(tr('export.sources'))}: "
                         f"{escape(sources)}</p>")

    # -- the whole file -----------------------------------------------------

    def pdf(self, title):
        document = QtGui.QTextDocument()
        for key, image in self.images.items():
            document.addResource(QtGui.QTextDocument.ResourceType.ImageResource.value,
                                 QtCore.QUrl(key), image)
        head = (f"<h1>{escape(title)}</h1><p style='color:#555'>"
                + escape(tr("export.generated", date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                            version=__version__)) + "</p>")
        document.setHtml("<html><body style='font-family: sans-serif; font-size: 10pt'>"
                         + head + "".join(self.html) + "<hr><p style='color:#555'>"
                         + escape(tr("export.credits")) + "</p></body></html>")
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        writer = QtGui.QPdfWriter(buffer)
        writer.setPageSize(QtGui.QPageSize(QtGui.QPageSize.PageSizeId.A4))
        writer.setResolution(110)
        document.setPageSize(QtCore.QSizeF(writer.width(), writer.height()))
        # PyQt6 names it print, PyQt5 print_
        (getattr(document, "print", None) or document.print_)(writer)
        buffer.close()
        return bytes(data)

    def save(self, path, title):
        self.files["informe.pdf"] = self.pdf(title)
        self.files["manifest.json"] = _json({
            "app": "PACHI / Field Shift", "version": __version__,
            "created": datetime.now().isoformat(timespec="seconds"),
            "files": sorted(self.files)})
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in self.files.items():
                archive.writestr(name, data)
        return sorted(self.files)


# (str path, list bundles, ExportOptions options)
# writes the ZIP of the fields; returns the names of the files in it
def write_zip(path, bundles, options):
    writer = _Writer()
    for bundle in bundles:
        writer.field(bundle, options)
    return writer.save(path, tr("export.title"))


# (str path, AnalysisResult result, Field field)
# writes the ZIP of one analysis (its report, JSON, CSV and pictures)
def write_analysis_zip(path, result, field):
    from fieldshift.analysis import get_analysis
    from fieldshift.export.collect import ExportOptions, FieldBundle
    options = ExportOptions(geojson=False, records=False)
    writer = _Writer()
    writer.field(FieldBundle(field, analyses=[result]), options)
    title = f"{tr(get_analysis(result.analysis_id).title_key)} · {field.name}"
    return writer.save(path, title)
