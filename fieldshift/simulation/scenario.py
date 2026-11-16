"""Field Shift scenarios: the same season of a field simulated with today's
weather (baseline) and with a shifted climate (warmer, less rain), and the
shifted climate with regulated deficit irrigation (small planned doses), to
see how much yield a climate shift costs and how much irrigation recovers.

    baseline, shifted, irrigated = run_scenario(field, FIELD_SHIFT)

The shift is applied to the season's daily weather (fieldshift.simulation
.weather): temperatures + temp_offset_c, rain x rain_scale, air humidity
(vapour pressure) raised with the temperature so the relative humidity stays
(Clausius-Clapeyron, ~7 % per °C). WOFOST 7.2 has no CO2 response, so CO2 is
not a parameter here.
"""

import math
from dataclasses import dataclass, replace

from fieldshift.simulation import weather as weather_mod
from fieldshift.simulation.run import season_start, model_inputs

# vapour pressure change per °C at constant relative humidity
VAP_PER_DEGREE = 0.07


# a climate shift: °C added to every day's min / max, factor on the rain,
# and the regulated deficit irrigation used in the third run: one dose of
# rdi_cm every rdi_every_days, from rdi_from_day after sowing
@dataclass(frozen=True)
class Scenario:
    temp_offset_c: float = 2.0
    rain_scale: float = 0.85
    rdi_cm: float = 2.0
    rdi_every_days: int = 14
    rdi_from_day: int = 30


# the default shift: a warmer (+2 °C) and drier (-15 % rain) season, the
# direction most projections give for central Chile by mid-century
FIELD_SHIFT = Scenario()


# (WeatherSeries series, Scenario scenario)
# a copy of the series with the scenario's climate shift
def shifted_series(series, scenario):
    factor = math.exp(math.log(1 + VAP_PER_DEGREE) * scenario.temp_offset_c)
    days = {date: replace(day, tmin=day.tmin + scenario.temp_offset_c,
                          tmax=day.tmax + scenario.temp_offset_c,
                          rain=day.rain * scenario.rain_scale, vap=day.vap * factor)
            for date, day in series.days.items()}
    return weather_mod.WeatherSeries(days, list(series.providers), series.elevation)


# (Scenario scenario, int max_duration)
# the regulated deficit irrigation doses [(days after sowing, cm)] of a season
def rdi_doses(scenario, max_duration):
    return [(day, scenario.rdi_cm)
            for day in range(scenario.rdi_from_day, int(max_duration), scenario.rdi_every_days)]


# (Field field, Scenario scenario = FIELD_SHIFT, dt.date today = None,
#  callable build_weather = None, callable simulate = None)
# (baseline, shifted, shifted with deficit irrigation) Simulations of the
# field's season, water-limited (the third one None when the field is marked
# irrigated: its potential run already has all the water it needs). raises
# like simulation.run.simulate
def run_scenario(field, scenario=FIELD_SHIFT, today=None, build_weather=None, simulate=None):
    import datetime as dt
    if simulate is None:
        from fieldshift.simulation.run import simulate
    today = today or dt.date.today()
    irrigated = bool((field.data.get("irrigated") or {}).get("value"))
    baseline = simulate(field, today=today, build_weather=build_weather, potential=irrigated)
    series = getattr(baseline, "series", None)
    if series is None:
        info, _site = model_inputs(field)
        lon = sum(v[0] for v in field.vertices) / len(field.vertices)
        lat = sum(v[1] for v in field.vertices) / len(field.vertices)
        sowing, _ = season_start(tuple(info["sowing_south"]), lat, today)
        end = sowing + dt.timedelta(days=int(info["max_duration"]) + 2)
        series = (build_weather or weather_mod.build_weather)(lat, lon, sowing, end, today)
    warmer = shifted_series(series, scenario)
    shifted = simulate(field, today=today, potential=irrigated, series=warmer)
    rdi = None
    if not irrigated:
        info, _site = model_inputs(field)
        rdi = simulate(field, today=today, potential=False, series=warmer,
                       irrigation=rdi_doses(scenario, info["max_duration"]))
    return baseline, shifted, rdi
