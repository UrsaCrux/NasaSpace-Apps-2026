"""Trends panel: the right column of the map tab while "Trends" is chosen,
with how one field behaved over the last 12 months. Scrolling: milestones,
seasons, then Weather, Growth and Soil & water (table left, 12-month chart
right, against the year before and the normal), and the crop. See
fieldshift.ui.field_panel.
"""

from fieldshift.i18n import tr

from fieldshift.trends import trends_report
from fieldshift.ui.field_panel import FieldPanel
from fieldshift.ui.trends_widgets import (
    CropCard, MilestonesCard, SeasonsCard, TrendSectionCard, long_month)


# the panel. open(layer_id) shows a field
class TrendsPanel(FieldPanel):

    title_key = "modes.trends"
    loading_key = "trends.loading"

    def __init__(self, view, fields, parent=None):
        self.sections = {}             # section id -> TrendSectionCard
        super().__init__(view, fields, parent)
        fields.records_changed.connect(self._on_records_changed)

    def _on_records_changed(self, layer_id):
        if layer_id == self.layer_id and self.report is not None:
            self.refresh()

    def make_report(self, field):
        return trends_report(field)

    def build(self, report):
        self.sections = {}
        first, last = report.months[0], report.months[-1]
        self.info_label.setText(tr("trends.info", start=long_month(first), end=long_month(last)))
        if report.milestones:
            self.milestones = MilestonesCard(report.milestones)
            self.content_layout.addWidget(self.milestones)
        if report.seasons:
            self.content_layout.addWidget(SeasonsCard(report.seasons))
        for section in report.sections:
            card = TrendSectionCard(section)
            self.content_layout.addWidget(card)
            self.sections[section.id] = card
        crop = CropCard(report.crop)
        crop.suggestion_requested.connect(lambda: self.suggestion_requested.emit(self.layer_id))
        self.content_layout.addWidget(crop)
        self.content_layout.addStretch(1)


