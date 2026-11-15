"""Follow-up of the crop from the farmer's records: days since sowing and the
newest plant height against the one before. Plain data, no Qt, no network.
"""

from dataclasses import dataclass
from datetime import date

from fieldshift.fields.records import latest, of_kind


# what the records tell about the crop; None where there is no record
@dataclass(frozen=True)
class Progress:
    sowing_date: str = None
    days_since_sowing: int = None
    height: float = None
    height_date: str = None
    height_change_pct: float = None


# (tuple records, date today = None)
# the Progress of a field's records
def crop_progress(records, today=None):
    today = today or date.today()
    sowing = latest(records, "sowing")
    heights = [r for r in of_kind(records, "plant_height") if r.value is not None]
    days = None
    if sowing is not None:
        days = (today - date.fromisoformat(sowing.date())).days
    change = None
    if len(heights) > 1 and heights[-2].value:
        change = (heights[-1].value - heights[-2].value) / heights[-2].value * 100
    return Progress(sowing.date() if sowing else None, days,
                    heights[-1].value if heights else None,
                    heights[-1].date() if heights else None, change)
