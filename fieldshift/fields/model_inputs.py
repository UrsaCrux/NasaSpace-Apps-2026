"""Hidden data a field carries for crop models, computed when it is saved.

  data["wofost"]     WOFOST crop model, crop, variety, sowing date, season
                     length and full parameters of the field's crop (None
                     when WOFOST has no model for it)   — crops/wofost_crops.py
  data["pcse_site"]  PCSE soil and site parameters of the terrain
                                                         — simulation/soil.py

The user never sees them; the crop growth analysis reads them. When PCSE is
not installed the WOFOST entry is stored as None with the reason.
"""

import sys

from fieldshift.fields.schema import CROP_KEY, PCSE_SITE_KEY, WOFOST_KEY


# (dict data)
# data (already normalized) with the hidden model inputs recomputed
def with_model_inputs(data):
    data = dict(data)
    crop = (data.get(CROP_KEY) or {}).get("value")
    data[WOFOST_KEY] = None
    if crop:
        try:
            from fieldshift.crops.wofost_crops import crop_info
            data[WOFOST_KEY] = crop_info(crop, (data.get(CROP_KEY) or {}).get("name"))
        except ImportError as exc:
            print(f"warning: no WOFOST crop data stored ({exc})", file=sys.stderr)
    from fieldshift.simulation.soil import site_descriptor
    data[PCSE_SITE_KEY] = site_descriptor(data)
    return data
