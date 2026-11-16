"""Climate shift analysis ("Field Shift"): how the season of the field's crop
would go in a warmer, drier climate, and what regulated deficit irrigation
recovers. Runs WOFOST 7.2 three times on the same season (see
fieldshift/simulation/scenario.py): today's weather, the shifted weather,
and the shifted weather with small planned irrigation doses.

Crops WOFOST has no model for (vines, orchards, berries...) get the same
shift on climate indices of the last 12 months instead (NASA POWER daily):
growing degree-days (base 10 °C, and the Winkler region for grapes), hot
days above the crop's limit, spring frosts, rain, and the crop's FAO
EcoCrop climate suitability — no made-up crop parameters.
"""

from fieldshift.analysis.crop_growth import SOURCES_BASE
from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW,
    PRIORITY_MEDIUM, AnalysisResult, DataSource, Metric, Recommendation, Series)

SOURCES = SOURCES_BASE
# sources of the climate-index comparison (crops without a model)
INDEX_SOURCES = (DataSource("NASA POWER", "analysis.var.tmax", "0.5° · daily"),
                 DataSource("FAO EcoCrop", "analysis.var.crop_limits", ""))
# Winkler regions (growing degree-days base 10 °C, Oct-Apr south / Apr-Oct north)
WINKLER = ((1389, "Ia–I"), (1667, "II"), (1944, "III"), (2222, "IV"), (99999, "V"))
GRAPES = ("wine_grape", "table_grape")
# a day with the transpiration below this share of the potential is stressed
STRESS_RFTRA = 0.7


def _result(field, series, metrics, summary, params, recs):
    return AnalysisResult("climate_shift", field.name, SOURCES, series, None, tuple(metrics),
                          summary, params, tuple(recs), placeholder=False)


def _yield_t(sim):
    return float(sim.summary.get("TWSO") or 0.0) / 1000


def _season_days(sim):
    rows = [r for r in sim.output if r.get("DVS") is not None]
    return len(rows)


def _stress_days(sim):
    return sum(1 for r in sim.output if r.get("RFTRA") is not None and r["RFTRA"] < STRESS_RFTRA)


# (Field field, callable run = None)
# AnalysisResult comparing today's climate with the shifted one (yield over
# the season of the shifted climate as the chart); a result that explains the
# reason when the field cannot be simulated
def run_climate_shift(field, run=None):
    from fieldshift.simulation.run import NotSimulable
    from fieldshift.simulation.scenario import FIELD_SHIFT
    scenario = FIELD_SHIFT
    try:
        if run is None:
            from fieldshift.simulation.scenario import run_scenario as run
        baseline, shifted, rdi = run(field, scenario)
    except NotSimulable as exc:
        reason = str(exc) if str(exc) in ("no_crop", "no_model") else "no_model"
        if reason == "no_model":
            return run_climate_indices(field, scenario)
        return _result(field, None, [Metric("analysis.climate_shift.m.status",
                                            f"analysis.crop_growth.status.{reason}",
                                            LEVEL_WARNING)],
                       f"analysis.crop_growth.summary_{reason}", {},
                       [Recommendation(f"analysis.crop_growth.rec.{reason}", {}, PRIORITY_HIGH)])
    except ImportError:
        return _result(field, None, [Metric("analysis.climate_shift.m.status",
                                            "analysis.crop_growth.status.no_pcse", LEVEL_BAD)],
                       "analysis.crop_growth.summary_no_pcse", {},
                       [Recommendation("analysis.crop_growth.rec.no_pcse", {}, PRIORITY_HIGH)])
    except Exception as exc:                       # weather sources down, model error...
        return _result(field, None, [Metric("analysis.climate_shift.m.status",
                                            "analysis.crop_growth.status.failed", LEVEL_BAD)],
                       "analysis.crop_growth.summary_failed", {"error": str(exc)[:200]},
                       [Recommendation("analysis.crop_growth.rec.failed", {}, PRIORITY_HIGH)])

    now_t, shift_t = _yield_t(baseline), _yield_t(shifted)
    change = 100 * (shift_t - now_t) / now_t if now_t > 0 else 0.0
    days_now, days_shift = _season_days(baseline), _season_days(shifted)
    stress_now, stress_shift = _stress_days(baseline), _stress_days(shifted)
    level = LEVEL_BAD if change <= -20 else LEVEL_WARNING if change <= -5 else LEVEL_GOOD
    metrics = [
        Metric("analysis.climate_shift.m.scenario", "analysis.climate_shift.scenario_text"),
        Metric("analysis.climate_shift.m.yield_now", f"{now_t:.1f} t/ha"),
        Metric("analysis.climate_shift.m.yield_shift", f"{shift_t:.1f} t/ha", level),
        Metric("analysis.climate_shift.m.change", f"{change:+.0f} %", level),
        Metric("analysis.climate_shift.m.season", f"{days_now} → {days_shift}",
               LEVEL_WARNING if days_shift < days_now - 7 else LEVEL_NEUTRAL),
        Metric("analysis.climate_shift.m.stress", f"{stress_now} → {stress_shift}",
               LEVEL_WARNING if stress_shift > stress_now + 5 else LEVEL_NEUTRAL),
    ]
    recs = []
    if rdi is not None:
        rdi_t = _yield_t(rdi)
        gained = rdi_t - shift_t
        doses = len(range(scenario.rdi_from_day, days_shift, scenario.rdi_every_days))
        water = doses * scenario.rdi_cm * 10                      # mm over the season
        metrics.append(Metric("analysis.climate_shift.m.yield_rdi", f"{rdi_t:.1f} t/ha",
                              LEVEL_GOOD if rdi_t >= now_t * 0.95 else LEVEL_WARNING))
        if gained > 0.05:
            recs.append(Recommendation("analysis.climate_shift.r.rdi", {
                "mm": f"{scenario.rdi_cm * 10:.0f}", "every": str(scenario.rdi_every_days),
                "gain": f"{gained:.1f}", "total": f"{water:.0f}"},
                PRIORITY_HIGH if change <= -10 else PRIORITY_MEDIUM))
    if change <= -5:
        recs.append(Recommendation("analysis.climate_shift.r.loss",
                                   {"pct": f"{abs(change):.0f}"}, PRIORITY_HIGH))
        recs.append(Recommendation("analysis.climate_shift.r.varieties", {}, PRIORITY_MEDIUM))
    else:
        recs.append(Recommendation("analysis.climate_shift.r.robust", {}, PRIORITY_MEDIUM))
    if days_shift < days_now - 7:
        recs.append(Recommendation("analysis.climate_shift.r.shorter",
                                   {"days": str(days_now - days_shift)}, PRIORITY_MEDIUM))
    if shifted.match == "proxy":
        recs.append(Recommendation("analysis.crop_growth.rec.proxy",
                                   {"model": f"crop.{shifted.crop_name}"}, PRIORITY_LOW))
    recs.append(Recommendation("analysis.climate_shift.r.about", {}, PRIORITY_LOW))

    rows = [r for r in shifted.output if r.get("TWSO") is not None]
    series = Series("analysis.var.yield_shift", "t/ha",
                    tuple(r["day"].isoformat() for r in rows),
                    tuple(round(float(r["TWSO"]) / 1000, 2) for r in rows)) if rows else None
    return _result(field, series, metrics, "analysis.climate_shift.summary",
                   {"now": f"{now_t:.1f}", "shift": f"{shift_t:.1f}", "pct": f"{change:+.0f}"},
                   recs)


# (float gdd)
# Winkler region name of a growing-degree-day sum
def winkler_region(gdd):
    return next(name for limit, name in WINKLER if gdd <= limit)


# (Field field, Scenario scenario)
# AnalysisResult for a crop without a growth model: the scenario's shift on
# the last 12 months of daily weather and on the crop's EcoCrop suitability
def run_climate_indices(field, scenario):
    from fieldshift import crops
    from fieldshift.analysis import real, sources
    try:
        months = sources.last_months(12)
        daily = real._daily(field, months)
        tmax, tmin = daily["T2M_MAX"], daily["T2M_MIN"]
        rain = daily.get("PRECTOTCORR", {})
        climate = real._field_climate(field)
    except Exception as exc:
        return real.unavailable("climate_shift", field, INDEX_SOURCES, exc)
    if len(tmax) < 200:
        return real.unavailable("climate_shift", field, INDEX_SOURCES, "too few days")
    _lon, lat = sources.center(field)
    growing = (10, 11, 12, 1, 2, 3, 4) if lat < 0 else (4, 5, 6, 7, 8, 9, 10)
    spring = (9, 10, 11) if lat < 0 else (3, 4, 5)
    info = real._safe(lambda: sources.crop_requirements(field))
    limit = (info.temperature.optimal_max if info and info.temperature.optimal_max
             else real.DEFAULT_HEAT_C)
    soil = {"ph": real._value(field, "ph"), "texture": real._value(field, "soil_texture")}

    def indices(offset, scale):
        gdd = sum(max(0.0, (tmax[d] + tmin[d]) / 2 + offset - 10)
                  for d in tmax if d in tmin and d.month in growing)
        hot = sum(1 for d, v in tmax.items() if v + offset >= limit)
        frost = sum(1 for d, v in tmin.items() if d.month in spring and v + offset <= 0)
        shifted_climate = dict(climate, temps=[t + offset for t in climate["temps"]],
                               min=[t + offset for t in climate["min"]],
                               rain=climate["rain"] * scale,
                               rain_months=[r * scale for r in climate["rain_months"]])
        score = real.crop_score(info, shifted_climate, soil, True)[0] if info else None
        return {"gdd": gdd, "hot": hot, "frost": frost,
                "rain": sum(rain.values()) * scale, "score": score}
    now = indices(0.0, 1.0)
    shift = indices(scenario.temp_offset_c, scenario.rain_scale)

    variety = crops.variety_by_id(real._value(field, "crop"))
    crop_id = variety.crop if variety else None
    crop_name = f"crop.{crop_id}" if crop_id else \
        ((field.data or {}).get("crop") or {}).get("name", "—")
    drop = (shift["score"] - now["score"]) if now["score"] is not None else None
    level = LEVEL_NEUTRAL if drop is None else \
        LEVEL_BAD if drop <= -20 else LEVEL_WARNING if drop <= -5 else LEVEL_GOOD
    gdd_text = f"{now['gdd']:.0f} → {shift['gdd']:.0f}"
    if crop_id in GRAPES:
        gdd_text += f" ({winkler_region(now['gdd'])} → {winkler_region(shift['gdd'])})"
    metrics = [
        Metric("analysis.climate_shift.m.scenario", "analysis.climate_shift.scenario_text"),
        Metric("analysis.climate_shift.m.model", "analysis.climate_shift.indices_mode"),
        Metric("analysis.climate_shift.m.suitability", "—" if now["score"] is None
               else f"{now['score']} % → {shift['score']} %", level),
        Metric("analysis.climate_shift.m.gdd", gdd_text,
               LEVEL_WARNING if shift["gdd"] - now["gdd"] > 250 else LEVEL_NEUTRAL),
        Metric("analysis.climate_shift.m.hot", f"{now['hot']} → {shift['hot']}",
               LEVEL_BAD if shift["hot"] > now["hot"] + 20 else
               LEVEL_WARNING if shift["hot"] > now["hot"] else LEVEL_GOOD),
        Metric("analysis.climate_shift.m.frost", f"{now['frost']} → {shift['frost']}"),
        Metric("analysis.climate_shift.m.rain", f"{now['rain']:.0f} → {shift['rain']:.0f} mm"),
    ]
    recs = []
    if crop_id in GRAPES and winkler_region(now["gdd"]) != winkler_region(shift["gdd"]):
        recs.append(Recommendation("analysis.climate_shift.r.winkler", {
            "before": winkler_region(now["gdd"]), "after": winkler_region(shift["gdd"])},
            PRIORITY_HIGH))
    if shift["hot"] > now["hot"]:
        recs.append(Recommendation("analysis.climate_shift.r.hot", {
            "days": str(shift["hot"] - now["hot"]), "limit": f"{limit:.0f}"},
            PRIORITY_HIGH if shift["hot"] - now["hot"] > 20 else PRIORITY_MEDIUM))
    if drop is not None and drop <= -5:
        recs.append(Recommendation("analysis.climate_shift.r.suitability",
                                   {"crop": crop_name, "pct": f"{abs(drop):.0f}"},
                                   PRIORITY_HIGH))
    recs.append(Recommendation("analysis.climate_shift.r.water", {
        "mm": f"{now['rain'] - shift['rain']:.0f}"}, PRIORITY_MEDIUM))
    if shift["frost"] < now["frost"]:
        recs.append(Recommendation("analysis.climate_shift.r.frost_less", {}, PRIORITY_LOW))
    recs.append(Recommendation("analysis.climate_shift.r.indices_about", {}, PRIORITY_LOW))

    # chart: degree-days building up over the year in the shifted climate
    by_month, total = [], 0.0
    for month in months:
        total += sum(max(0.0, (tmax[d] + tmin[d]) / 2 + scenario.temp_offset_c - 10)
                     for d in tmax if d in tmin and real._month_of(d) == month
                     and d.month in growing)
        by_month.append(round(total))
    series = Series("analysis.var.gdd_shift", "°C·d", tuple(months), tuple(by_month))
    return AnalysisResult("climate_shift", field.name, INDEX_SOURCES, series, None,
                          tuple(metrics), "analysis.climate_shift.summary_indices",
                          {"crop": crop_name, "now": "—" if now["score"] is None else
                           str(now["score"]), "shift": "—" if shift["score"] is None else
                           str(shift["score"]), "gdd": f"{shift['gdd'] - now['gdd']:.0f}"},
                          tuple(recs), placeholder=False)
