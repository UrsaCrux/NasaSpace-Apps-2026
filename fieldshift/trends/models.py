"""What the Trends panel shows for one field: the last 12 months, month by
month, against the year before and the long-term normal. Plain data, no Qt.
"""

from dataclasses import dataclass

from fieldshift.status.models import CHART_BARS, CHART_LINE  # noqa: F401

# how the months of a row add up for the year
AGG_SUM = "sum"
AGG_MEAN = "mean"


def _total(values, aggregate):
    known = [v for v in values if v is not None]
    if not known:
        return None
    return sum(known) if aggregate == AGG_SUM else sum(known) / len(known)


# one variable over the months ("2025-12"..): values of the last 12 months,
# of the same months one year before (previous) and the long-term normal
# (normal); None where unknown. previous / normal are None when the source
# has none
@dataclass(frozen=True)
class TrendRow:
    key: str
    label_key: str
    unit: str
    months: tuple
    values: tuple
    previous: tuple = None
    normal: tuple = None
    aggregate: str = AGG_MEAN
    chart: str = CHART_LINE
    decimals: int = 1
    source: str = ""

    # ()
    # the year's total (sums) or mean (means) of values, or None
    def total(self):
        return _total(self.values, self.aggregate)

    # ()
    # the same for the year before, or None
    def previous_total(self):
        return _total(self.previous, self.aggregate) if self.previous else None

    # ()
    # the same for the normal, or None
    def normal_total(self):
        return _total(self.normal, self.aggregate) if self.normal else None


# a group of rows: "weather", "growth" or "soil"
@dataclass(frozen=True)
class TrendSection:
    id: str
    title_key: str
    icon: str
    rows: tuple


# a notable fact of the year: label_key filled with value and month
# ("Wettest month: March 2026, 142 mm")
@dataclass(frozen=True)
class Milestone:
    icon: str
    label_key: str
    value: str
    month: str = ""


# one season of the year: name key ("trends.season.summer"), the year it
# started in, its months and {column key: value or None}
@dataclass(frozen=True)
class SeasonRow:
    name_key: str
    year: str
    months: tuple
    values: dict


# everything shown for one field. example True for made-up numbers (tests);
# missing: api.errors.DataError of the sources that did not answer
@dataclass(frozen=True)
class TrendsReport:
    field_name: str
    months: tuple
    sections: tuple
    milestones: tuple
    seasons: tuple
    crop: str = None
    example: bool = True
    missing: tuple = ()

    # (str section_id)
    # the section with that id, or None
    def section(self, section_id):
        return next((s for s in self.sections if s.id == section_id), None)
