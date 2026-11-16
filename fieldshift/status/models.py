"""What the Status panel shows for one field: today and the coming days.
Plain data, no Qt. (The past is in Trends.)

Texts the user reads are i18n keys (``*_key``) plus values to fill them,
so the same report can be shown in every language.
"""

from dataclasses import dataclass, field

# how a value or a warning looks: decides its colour in the UI
LEVEL_OK = "ok"
LEVEL_WATCH = "watch"
LEVEL_ALERT = "alert"

# how a series is drawn in a chart (Trends)
CHART_LINE = "line"
CHART_BARS = "bars"

# (float value, int decimals = 0)
# the value as text, never "-0" ("-0.2" with 0 decimals is "0")
def num(value, decimals=0):
    text = f"{value:.{decimals}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text


# how many coming days the user can choose to see (the forecast service
# gives at most 16)
HORIZONS = (7, 14)
FORECAST_DAYS = 16


# one value of today: label_key + value in unit, and a short note under it
# (note_key filled with note_params). value None: not available. measured
# is the time ("HH:MM") of the farmer's measurement used instead of the
# forecast's value, "" when the value is the forecast's
@dataclass(frozen=True)
class TodayTile:
    key: str
    icon: str
    label_key: str
    value: float
    unit: str = ""
    decimals: int = 0
    note_key: str = ""
    note_params: dict = field(default_factory=dict)
    level: str = LEVEL_OK
    measured: str = ""


# a light warning about a coming day (date "YYYY-MM-DD"): text_key filled
# with params
@dataclass(frozen=True)
class StatusAlert:
    text_key: str
    params: dict = field(default_factory=dict)
    level: str = LEVEL_WATCH
    date: str = ""


# follow-up of the crop: its name and the two newest NDVI images (value and
# date "YYYY-MM-DD"; previous None when there is only one)
@dataclass(frozen=True)
class Tracking:
    crop: str
    ndvi: float
    date: str
    previous: float = None
    previous_date: str = ""

    # ()
    # change of the NDVI against the image before, %, or None
    def change_pct(self):
        if self.previous in (None, 0):
            return None
        return (self.ndvi - self.previous) / abs(self.previous) * 100


# everything shown for one field: today's tiles, the forecast
# (api.forecast.Forecast: days, today first, and hours) and the warnings of
# the coming days. example True when the numbers are made up (tests)
@dataclass(frozen=True)
class StatusReport:
    field_name: str
    tiles: tuple
    forecast: object
    alerts: tuple
    example: bool = False

    # (int days)
    # the warnings of the first days of the forecast
    def alerts_within(self, days):
        dates = {d.date for d in self.forecast.days[:days]}
        return [a for a in self.alerts if a.date in dates]
