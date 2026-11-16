"""Climate shift analysis ("Field Shift"): how the season of the field's crop
would go in a warmer, drier climate, and what regulated deficit irrigation
recovers. Runs WOFOST 7.2 three times on the same season (see
fieldshift/simulation/scenario.py): today's weather, the shifted weather,
and the shifted weather with small planned irrigation doses.
"""

from fieldshift.analysis.crop_growth import SOURCES_BASE
from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW,
    PRIORITY_MEDIUM, AnalysisResult, Metric, Recommendation, Series)

SOURCES = SOURCES_BASE
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
