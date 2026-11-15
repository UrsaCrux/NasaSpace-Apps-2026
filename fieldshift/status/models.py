"""What the Status panel shows for one field. Plain data, no Qt.

Texts the user reads are i18n keys (``*_key``) plus values to fill them,
so the same report can be shown in every language.
"""

from dataclasses import dataclass, field

# how a value or an alert looks: decides its colour in the UI
LEVEL_OK = "ok"
LEVEL_WATCH = "watch"
LEVEL_ALERT = "alert"

# how a row is drawn in the chart
CHART_LINE = "line"
CHART_BARS = "bars"

# periods (days back) the user can choose; longer periods belong to Trends
PERIODS = (7, 14, 30)


# one variable of a section ("Rain", mm): one value per day in dates
# ("2026-11-14"), oldest first. fixed rows (pH from a soil map) have a single
# value and no chart. source names the product ("GPM IMERG"), not translated
@dataclass(frozen=True)
class StatusRow:
    key: str
    label_key: str
    unit: str
    dates: tuple
    values: tuple
    chart: str = CHART_LINE
    source: str = ""
    fixed: bool = False
    level: str = LEVEL_OK
    decimals: int = 1

    # ()
    # the newest value
    def latest(self):
        return self.values[-1]

    # ()
    # mean of the values
    def mean(self):
        return sum(self.values) / len(self.values)

    # ()
    # change of the newest value against the mean of the period (0 when fixed)
    def change(self):
        return 0.0 if self.fixed else self.latest() - self.mean()


# a warning of a section: text_key filled with params. upcoming alerts are
# about the next days (short forecast); suggestion True links to Analyze
@dataclass(frozen=True)
class StatusAlert:
    text_key: str
    params: dict = field(default_factory=dict)
    level: str = LEVEL_WATCH
    upcoming: bool = False
    suggestion: bool = False


# one tile of the "today" summary: the row it comes from and its value
@dataclass(frozen=True)
class SummaryTile:
    section: str
    row: StatusRow
    icon: str


# a section of the report: "weather", "growth" or "soil". note_key / params
# is a line shown under the title (crop stage); texture holds the
# analysis.models.TextureFigure of the soil section
@dataclass(frozen=True)
class StatusSection:
    id: str
    title_key: str
    icon: str
    rows: tuple
    alerts: tuple = ()
    note_key: str = ""
    note_params: dict = field(default_factory=dict)
    texture: object = None


# everything shown for one field and period. example True while the numbers
# are made up
@dataclass(frozen=True)
class StatusReport:
    field_name: str
    days: int
    last_date: str
    sections: tuple
    summary: tuple
    example: bool = True

    # (str section_id)
    # the section with that id, or None
    def section(self, section_id):
        return next((s for s in self.sections if s.id == section_id), None)

    # ()
    # every alert of every section, in section order
    def alerts(self):
        return [a for s in self.sections for a in s.alerts]
