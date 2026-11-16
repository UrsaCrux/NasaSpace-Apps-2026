"""What an analysis needs and what it returns. Plain data, no Qt.

Texts the user reads are i18n keys (``*_key``) plus values to fill them,
so the same result can be shown in every language.
"""

from dataclasses import dataclass, field

# how good a metric is: decides its colour in the UI
LEVEL_GOOD = "good"
LEVEL_WARNING = "warning"
LEVEL_BAD = "bad"
LEVEL_NEUTRAL = "neutral"

# how urgent a recommendation is
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"


# one data set an analysis reads. name is the product ("ERA5-Land"), which
# is not translated; variable_key names the variable in the i18n files;
# detail is resolution / frequency ("9 km · daily")
@dataclass(frozen=True)
class DataSource:
    name: str
    variable_key: str
    detail: str = ""


# the values the analysis looks at over time: one value per date
# ("2025-07"), in unit
@dataclass(frozen=True)
class Series:
    label_key: str
    unit: str
    dates: tuple
    values: tuple
    label_params: dict = field(default_factory=dict)    # fills label_key ("{crop}")


# what the map shows over time: for each date a square grid of values
# covering the field's bounding box (rows north to south). palette is one of
# "temperature", "vegetation", "water", "suitability"; low / high fix the
# colour scale
@dataclass(frozen=True)
class MapFrames:
    label_key: str
    unit: str
    dates: tuple
    grids: tuple
    low: float
    high: float
    palette: str


# one number of the result ("Frost days: 23"); value is already formatted
@dataclass(frozen=True)
class Metric:
    label_key: str
    value: str
    level: str = LEVEL_NEUTRAL


# one piece of advice: text_key filled with params, and how urgent it is
@dataclass(frozen=True)
class Recommendation:
    text_key: str
    params: dict = field(default_factory=dict)
    priority: str = PRIORITY_MEDIUM


# a soil texture triangle (USDA classes) with the field's point: clay, sand
# and silt in % (None when unknown) and its texture class key
# (schema.TEXTURES, None when unknown)
@dataclass(frozen=True)
class TextureFigure:
    clay: float = None
    sand: float = None
    silt: float = None
    texture: str = None


# everything one analysis found for one field. placeholder is True while
# the numbers are made up (the UI says so). series / frames may be None for
# results without a time line (then the tab shows the figure, e.g. a
# TextureFigure, in their place)
@dataclass(frozen=True)
class AnalysisResult:
    analysis_id: str
    field_name: str
    sources: tuple
    series: Series
    frames: MapFrames
    metrics: tuple
    summary_key: str
    summary_params: dict
    recommendations: tuple
    placeholder: bool = True
    figure: object = None


# an analysis the user can choose. title_key / short_key / description_key
# are i18n keys; run(field) returns an AnalysisResult
@dataclass(frozen=True)
class Analysis:
    id: str
    title_key: str
    short_key: str
    description_key: str
    sources: tuple
    run: object
