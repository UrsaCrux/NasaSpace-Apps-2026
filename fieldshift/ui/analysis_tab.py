"""One tab per analysis result, split in four:

    +---------------------------+---------------------------+
    | Data: sources, chart and  | Map: the field coloured   |
    | a time slider (play)      | for the selected date     |
    +---------------------------+---------------------------+
    | Results: summary and      | Recommendations, most     |
    | key numbers               | urgent first              |
    +---------------------------+---------------------------+

The slider moves the chart cursor and the map together. Every part can be
resized with the splitters.
"""

from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM)
from fieldshift.analysis.registry import get_analysis
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui.analysis_widgets import (
    FieldPreview, LineChart, figure_widget, format_date, localize, series_title)

# time between dates while playing (ms)
PLAY_STEP_MS = 600

_LEVEL_COLORS = {LEVEL_GOOD: "#2e7d32", LEVEL_WARNING: "#ef8f00", LEVEL_BAD: "#c62828"}
# priority tags: neutral tones (no green / red traffic light, which read like
# the good / bad colours of the charts and maps)
_PRIORITY_COLORS = {PRIORITY_HIGH: "#8e2b20", PRIORITY_MEDIUM: "#7a5a00", PRIORITY_LOW: "#546e7a"}
_PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}


# (dict params)
# the params of a text with their i18n keys translated ("month.7" -> "July")
def localize_params(params):
    return {key: localize(value) for key, value in params.items()}


# the four-part view of one AnalysisResult for one field
class AnalysisTab(QtWidgets.QWidget):

    # (AnalysisResult result, Field field, QWidget parent = None)
    # builds the four parts; the time slider starts on the last date
    def __init__(self, result, field, parent=None):
        super().__init__(parent)
        self.result = result
        self.field = field
        self.analysis = get_analysis(result.analysis_id)
        self._play_timer = QtCore.QTimer(self)
        self._play_timer.setInterval(PLAY_STEP_MS)
        self._play_timer.timeout.connect(self._play_step)

        # results without a time line (series is None) show their figure
        # instead of the chart; without map frames there is no map part
        self.has_series = result.series is not None
        top = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        top.addWidget(self._build_data_box())
        if result.frames is not None:
            top.addWidget(self._build_map_box())
        bottom = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        bottom.addWidget(self._build_results_box())
        bottom.addWidget(self._build_recommendations_box())
        for splitter in (top, bottom):
            splitter.setSizes([600, 400])
        rows = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        rows.addWidget(top)
        rows.addWidget(bottom)
        # nothing to draw over time (e.g. perennial crops in Rotation): the
        # data box only lists the sources, so it takes little room
        empty_top = not self.has_series and result.frames is None and result.figure is None
        rows.setSizes([110, 670] if empty_top else [480, 300])

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(self._build_header())
        layout.addWidget(rows, 1)
        if self.has_series:
            self.set_date_index(len(result.series.dates) - 1)

    # ()
    # title of the tab: "<short name> · <field>"
    def tab_title(self):
        return tr("analysis.tab_title", analysis=tr(self.analysis.short_key),
                  field=self.result.field_name)

    # (int index)
    # shows the date number index in the chart, the map and the labels
    def set_date_index(self, index):
        if not self.has_series:
            return
        series = self.result.series
        index = max(0, min(index, len(series.dates) - 1))
        if self.slider.value() != index:
            self.slider.setValue(index)            # comes back here through the signal
            return
        self.chart.set_cursor(index)
        if self.result.frames is not None:
            self.preview.set_frame(index)
        date = format_date(series.dates[index])
        value = f"{series.values[index]:g} {series.unit}".strip()
        self.date_label.setText(date)
        self.value_label.setText(tr("analysis.value_at", label=series_title(series),
                                    date=date, value=value))
        if self.result.frames is not None:
            self.map_title.setText(f"{series_title(self.result.frames)} — {date}")

    # ()
    # index of the date shown
    def date_index(self):
        return self.slider.value() if self.has_series else 0

    # (bool playing)
    # starts or stops moving through the dates
    def set_playing(self, playing):
        if not self.has_series:
            return
        if playing:
            self._play_timer.start()
        else:
            self._play_timer.stop()
        self.play_button.setChecked(playing)
        self.play_button.setText("⏸" if playing else "▶")
        self.play_button.setToolTip(tr("analysis.pause") if playing else tr("analysis.play"))

    # -- building blocks ---------------------------------------------------

    # (str path = None)
    # writes this analysis (report, JSON, CSV, pictures) to a ZIP, asking
    # where when no path is given. returns the files written, or []
    def export(self, path=None):
        from fieldshift.export.write import safe_name, write_analysis_zip
        from fieldshift.ui import dialogs
        from fieldshift.ui.export_dialog import ask_zip_path
        if path is None:
            path = ask_zip_path(self, f"PACHI_{safe_name(self.result.field_name)}_"
                                      f"{self.result.analysis_id}.zip")
            if path is None:
                return []
        try:
            files = write_analysis_zip(path, self.result, self.field)
        except OSError as exc:
            dialogs.inform(self, tr("export.title"), tr("fields.export_failed", error=exc))
            return []
        dialogs.inform(self, tr("export.title"), tr("export.done_one", path=path))
        return files

    def _build_header(self):
        title = QtWidgets.QLabel(f"<h2>{tr(self.analysis.title_key)} · {self.result.field_name}</h2>")
        row = QtWidgets.QHBoxLayout()
        row.addWidget(title)
        if self.has_series and self.result.series.dates:
            dates = self.result.series.dates
            period = QtWidgets.QLabel(tr("analysis.period", start=format_date(dates[0]),
                                         end=format_date(dates[-1])))
            period.setStyleSheet("color: #555;")
            row.addWidget(period)
        row.addStretch(1)
        self.export_button = QtWidgets.QPushButton(tr("export.this_analysis"))
        self.export_button.clicked.connect(lambda: self.export())
        row.addWidget(self.export_button)
        if self.result.placeholder:
            self.example_badge = QtWidgets.QLabel(tr("analysis.example_data"))
            self.example_badge.setToolTip(tr("analysis.example_tooltip"))
            self.example_badge.setStyleSheet(
                "background: #fff3c4; color: #7a5b00; border: 1px solid #e6c34d;"
                " border-radius: 10px; padding: 3px 10px; font-weight: bold;")
            row.addWidget(self.example_badge)
        return row

    def _build_data_box(self):
        box = QtWidgets.QGroupBox(tr("analysis.data"))
        sources = "<br>".join(
            f"• <b>{s.name}</b> — {tr(s.variable_key)}" + (f" <span style='color:#777'>({s.detail})</span>"
                                                          if s.detail else "")
            for s in self.result.sources)
        sources_label = QtWidgets.QLabel(f"{tr('analysis.sources')}<br>{sources}")
        sources_label.setWordWrap(True)
        if not self.has_series:
            layout = QtWidgets.QVBoxLayout(box)
            layout.addWidget(sources_label)
            self.figure = figure_widget(self.result.figure)
            if self.figure is not None:
                layout.addWidget(self.figure, 1)
            else:
                layout.addStretch(1)
            return box
        self.chart = LineChart(self.result.series)

        self.play_button = QtWidgets.QPushButton("▶")
        self.play_button.setCheckable(True)
        self.play_button.setFixedWidth(40)
        self.play_button.setToolTip(tr("analysis.play"))
        self.play_button.clicked.connect(self.set_playing)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, len(self.result.series.dates) - 1)
        self.slider.setValue(len(self.result.series.dates) - 1)
        self.slider.valueChanged.connect(self.set_date_index)
        self.date_label = QtWidgets.QLabel()
        self.date_label.setMinimumWidth(110)
        time_row = QtWidgets.QHBoxLayout()
        time_row.addWidget(self.play_button)
        time_row.addWidget(self.slider, 1)
        time_row.addWidget(self.date_label)
        self.value_label = QtWidgets.QLabel()
        self.value_label.setStyleSheet("font-weight: bold;")

        layout = QtWidgets.QVBoxLayout(box)
        layout.addWidget(sources_label)
        layout.addWidget(self.chart, 1)
        layout.addLayout(time_row)
        layout.addWidget(self.value_label)
        return box

    def _build_map_box(self):
        box = QtWidgets.QGroupBox(tr("analysis.map"))
        self.map_title = QtWidgets.QLabel()
        self.map_title.setStyleSheet("font-weight: bold;")
        self.preview = FieldPreview(self.field.vertices, self.result.frames)
        layout = QtWidgets.QVBoxLayout(box)
        layout.addWidget(self.map_title)
        layout.addWidget(self.preview, 1)
        return box

    def _build_results_box(self):
        box = QtWidgets.QGroupBox(tr("analysis.results"))
        summary = QtWidgets.QLabel(tr(self.result.summary_key,
                                      **localize_params(self.result.summary_params)))
        summary.setWordWrap(True)
        cards = QtWidgets.QGridLayout()
        self.metric_cards = []
        for i, metric in enumerate(self.result.metrics):
            card = QtWidgets.QFrame()
            card.setStyleSheet("QFrame { background: white; border: 1px solid #ddd; border-radius: 6px; }"
                               "QLabel { border: none; }")
            value = QtWidgets.QLabel(localize(metric.value))
            value.setWordWrap(True)
            color = _LEVEL_COLORS.get(metric.level, "#222222")
            value.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")
            label = QtWidgets.QLabel(tr(metric.label_key))
            label.setWordWrap(True)
            label.setStyleSheet("color: #555;")
            inner = QtWidgets.QVBoxLayout(card)
            inner.addWidget(value)
            inner.addWidget(label)
            cards.addWidget(card, i // 2, i % 2)
            self.metric_cards.append((value, label))
        layout = QtWidgets.QVBoxLayout(box)
        layout.addWidget(summary)
        layout.addLayout(cards)
        layout.addStretch(1)
        return box

    def _build_recommendations_box(self):
        box = QtWidgets.QGroupBox(tr("analysis.recommendations"))
        content = QtWidgets.QWidget()
        rows = QtWidgets.QVBoxLayout(content)
        self.recommendation_labels = []
        ordered = sorted(self.result.recommendations,
                         key=lambda r: _PRIORITY_ORDER.get(r.priority, 1))
        for rec in ordered:
            color = _PRIORITY_COLORS.get(rec.priority, "#777777")
            priority = tr(f"analysis.priority.{rec.priority}")
            text = tr(rec.text_key, **localize_params(rec.params))
            label = QtWidgets.QLabel(
                f"<span style='color:{color}; font-size:11px; font-weight:bold'>"
                f"[{priority.upper()}]</span>&nbsp; {text}")
            label.setWordWrap(True)
            label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            rows.addWidget(label)
            self.recommendation_labels.append(label)
        rows.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        layout = QtWidgets.QVBoxLayout(box)
        layout.addWidget(scroll)
        return box

    def _play_step(self):
        last = len(self.result.series.dates) - 1
        self.set_date_index(0 if self.date_index() >= last else self.date_index() + 1)

    def hideEvent(self, event):
        self.set_playing(False)                  # do not play in a hidden tab
        super().hideEvent(event)
