"""Run WOFOST 7.2 (PCSE) for a field: water-limited production with free
drainage (Wofost72_WLP_FD) for rain-fed fields, potential production
(Wofost72_PP, no water shortage) for fields marked as irrigated.

Inputs come from the field file: the crop model and parameters
(data["wofost"]) and the soil / site descriptor (data["pcse_site"]); fields
saved before those existed get them computed on the fly. The season:

* if the crop's usual sowing date was less than IN_SEASON_DAYS ago, the
  current season is simulated from that date (observed weather until today,
  then forecast, then climate);
* otherwise the next season, from the next sowing date.

Sowing dates are for the southern hemisphere and move 6 months north of the
equator.
"""

import datetime as dt
from dataclasses import dataclass

from fieldshift.simulation import weather as weather_mod

# a season sown less than this many days ago is "in progress"
IN_SEASON_DAYS = 120
# daily outputs kept from the model
OUTPUT_VARS = ("DVS", "LAI", "TAGP", "TWSO", "SM", "RD")


# raised when the field cannot be simulated (no crop, crop without model...)
class NotSimulable(Exception):
    pass


# what a simulation produced
@dataclass
class Simulation:
    crop_name: str
    variety_name: str
    match: str                 # "exact" or "proxy"
    sowing: dt.date
    in_season: bool
    output: list               # one dict per day: day, DVS, LAI, TAGP, TWSO, SM, RD
    summary: dict              # PCSE summary output (one season)
    weather_counts: dict       # {"observed": n, "forecast": n, "climate": n}
    weather_providers: list
    site: dict                 # the soil / site descriptor used
    irrigated: bool            # True: potential production (no water stress)


# ((int, int) sowing_south, float lat, dt.date today)
# (sowing date, in_season) of the season to simulate
def season_start(sowing_south, lat, today):
    month, day = sowing_south
    if lat > 0:
        month = (month + 5) % 12 + 1                   # +6 months in the north
    candidates = [dt.date(year, month, min(day, 28)) for year in
                  (today.year - 1, today.year, today.year + 1)]
    past = [d for d in candidates if d <= today]
    if past and (today - past[-1]).days <= IN_SEASON_DAYS:
        return past[-1], True
    return next(d for d in candidates if d > today), False


# (Field field)
# (wofost info, site descriptor) of a field, computed when the file lacks them
def model_inputs(field):
    from fieldshift.fields.model_inputs import with_model_inputs
    from fieldshift.fields.schema import CROP_KEY, PCSE_SITE_KEY, WOFOST_KEY
    data = field.data
    crop = (data.get(CROP_KEY) or {}).get("value")
    if not crop:
        raise NotSimulable("no_crop")
    if data.get(WOFOST_KEY) is None or data.get(PCSE_SITE_KEY) is None:
        data = with_model_inputs(data)
    if data.get(WOFOST_KEY) is None:
        raise NotSimulable("no_model")
    return data[WOFOST_KEY], data[PCSE_SITE_KEY]


# (Field field, dt.date today = None, callable build_weather = None,
#  bool potential = None)
# runs the season and returns a Simulation; raises NotSimulable, or
# RuntimeError when there is no weather. potential=None follows the field's
# "irrigated" value; True / False force potential / water-limited production
def simulate(field, today=None, build_weather=None, potential=None, series=None):
    from pcse.base import ParameterProvider
    from pcse.models import Wofost72_PP, Wofost72_WLP_FD

    today = today or dt.date.today()
    info, site = model_inputs(field)
    lon = sum(v[0] for v in field.vertices) / len(field.vertices)
    lat = sum(v[1] for v in field.vertices) / len(field.vertices)
    sowing, in_season = season_start(tuple(info["sowing_south"]), lat, today)
    end = sowing + dt.timedelta(days=int(info["max_duration"]) + 2)
    if potential is None:
        potential = bool((field.data.get("irrigated") or {}).get("value"))
    if series is None:
        series = (build_weather or weather_mod.build_weather)(lat, lon, sowing, end, today)
    elevation = (site.get("inputs") or {}).get("elevation_m")
    if elevation is not None and not series.elevation:
        series.elevation = float(elevation)
    weather = weather_mod.pcse_provider(series, lat, lon)

    crop = info["crop_name"], info["variety_name"]
    params = ParameterProvider(cropdata=_CropData(crop, info["parameters"]),
                               soildata=dict(site["soil"]), sitedata=dict(site["site"]))
    agro = [{sowing: {
        "CropCalendar": {"crop_name": crop[0], "variety_name": crop[1],
                         "crop_start_date": sowing, "crop_start_type": "sowing",
                         "crop_end_date": None, "crop_end_type": "maturity",
                         "max_duration": int(info["max_duration"])},
        "TimedEvents": None, "StateEvents": None}}]
    model = (Wofost72_PP if potential else Wofost72_WLP_FD)(params, weather, agro)
    model.run_till_terminate()
    output = [{k: row.get(k) for k in ("day",) + OUTPUT_VARS} for row in model.get_output()]
    summary = (model.get_summary_output() or [{}])[0]
    result = Simulation(crop[0], crop[1], info.get("match", "exact"), sowing, in_season, output,
                        summary, series.counts(), list(series.providers), site, potential)
    result.series = series                     # reused for a second run (potential yield)
    return result


# the stored parameters as the crop data PCSE asks for (it calls
# set_active_crop with the agromanagement's crop and variety)
class _CropData(dict):
    def __init__(self, crop, parameters):
        super().__init__(parameters)
        self.crop = crop

    def set_active_crop(self, crop_name=None, variety_name=None):
        if (crop_name, variety_name) != self.crop:
            raise NotSimulable(f"stored parameters are for {self.crop}")
