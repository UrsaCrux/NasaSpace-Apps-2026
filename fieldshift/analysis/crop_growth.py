"""Crop growth analysis: simulates the season of the field's crop with
WOFOST 7.2 (PCSE) — the crop model stored in the field file, its soil /
site descriptor and the weather: observed, then forecast, then the zone's
climate (last year's weather on the same days) for the rest of the season.
See fieldshift/simulation.
"""

from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW,
    PRIORITY_MEDIUM, AnalysisResult, DataSource, MapFrames, Metric, Recommendation, Series)

SOURCES_BASE = (DataSource("WOFOST 7.2 (PCSE)", "analysis.var.crop_model", ""),
                DataSource("SoilGrids", "analysis.var.soil", "250 m"))
# share of the season from the climate above which the result is flagged
CLIMATE_WARNING_SHARE = 0.5


def _result(field, sources, series, frames, metrics, summary, params, recs):
    return AnalysisResult("crop_growth", field.name, sources, series, frames, tuple(metrics),
                          summary, params, tuple(recs), placeholder=False)


# (Field field, callable simulate = None)
# AnalysisResult of the simulated season (LAI over time); a result that
# explains the reason when the field cannot be simulated
def run_crop_growth(field, simulate=None):
    from fieldshift.simulation.run import NotSimulable
    try:
        if simulate is None:
            from fieldshift.simulation.run import simulate
        main = simulate(field)
        potential = main if main.irrigated else simulate(field, potential=True,
                                                         series=getattr(main, "series", None))
    except NotSimulable as exc:
        reason = str(exc) if str(exc) in ("no_crop", "no_model") else "no_model"
        return _result(field, SOURCES_BASE, None, None,
                       [Metric("analysis.crop_growth.metric.status",
                               f"analysis.crop_growth.status.{reason}", LEVEL_WARNING)],
                       f"analysis.crop_growth.summary_{reason}", {},
                       [Recommendation(f"analysis.crop_growth.rec.{reason}", {}, PRIORITY_HIGH)])
    except ImportError:
        return _result(field, SOURCES_BASE, None, None,
                       [Metric("analysis.crop_growth.metric.status",
                               "analysis.crop_growth.status.no_pcse", LEVEL_BAD)],
                       "analysis.crop_growth.summary_no_pcse", {},
                       [Recommendation("analysis.crop_growth.rec.no_pcse", {}, PRIORITY_HIGH)])
    except Exception as exc:                       # weather sources down, model error...
        return _result(field, SOURCES_BASE, None, None,
                       [Metric("analysis.crop_growth.metric.status",
                               "analysis.crop_growth.status.failed", LEVEL_BAD)],
                       "analysis.crop_growth.summary_failed", {"error": str(exc)[:200]},
                       [Recommendation("analysis.crop_growth.rec.failed", {}, PRIORITY_HIGH)])

    rows = [r for r in main.output if r.get("LAI") is not None]
    dates = tuple(r["day"].isoformat() for r in rows)
    lai = tuple(round(float(r["LAI"]), 2) for r in rows)
    top = max(max(lai, default=0), 1.0)
    series = Series("analysis.var.lai", "m²/m²", dates, lai)
    frames = MapFrames("analysis.var.lai", "m²/m²", dates, tuple(((v,),) for v in lai), 0.0,
                       round(top, 2), "vegetation")
    summ = main.summary
    yield_t = (summ.get("TWSO") or 0) / 1000
    biomass_t = (summ.get("TAGP") or 0) / 1000
    potential_t = (potential.summary.get("TWSO") or 0) / 1000
    gap = 1 - yield_t / potential_t if potential_t > 0 else 0
    maturity = summ.get("DOM")
    counts = main.weather_counts
    total = sum(counts.values()) or 1
    climate_share = counts.get("climate", 0) / total
    crop_key = f"analysis.crop_growth.crop.{main.crop_name}"
    metrics = [
        Metric("analysis.crop_growth.metric.yield", f"{yield_t:.1f} t/ha",
               LEVEL_BAD if gap > 0.6 else LEVEL_WARNING if gap > 0.25 else LEVEL_GOOD),
        Metric("analysis.crop_growth.metric.potential", f"{potential_t:.1f} t/ha"),
        Metric("analysis.crop_growth.metric.biomass", f"{biomass_t:.1f} t/ha"),
        Metric("analysis.crop_growth.metric.lai", f"{max(lai, default=0):.1f}"),
        Metric("analysis.crop_growth.metric.maturity",
               maturity.isoformat() if maturity else "analysis.crop_growth.not_mature",
               LEVEL_NEUTRAL if maturity else LEVEL_WARNING),
        Metric("analysis.crop_growth.metric.weather",
               f"{counts.get('observed', 0)} / {counts.get('forecast', 0)} / "
               f"{counts.get('climate', 0)}",
               LEVEL_WARNING if climate_share > CLIMATE_WARNING_SHARE else LEVEL_NEUTRAL),
    ]
    recs = []
    if not main.irrigated and gap > 0.25:
        recs.append(Recommendation("analysis.crop_growth.rec.water_gap",
                                   {"gap": f"{gap * 100:.0f} %", "potential": f"{potential_t:.1f}"},
                                   PRIORITY_HIGH if gap > 0.6 else PRIORITY_MEDIUM))
    if main.match == "proxy":
        recs.append(Recommendation("analysis.crop_growth.rec.proxy", {"model": crop_key},
                                   PRIORITY_MEDIUM))
    if climate_share > 0:
        recs.append(Recommendation("analysis.crop_growth.rec.climate",
                                   {"share": f"{climate_share * 100:.0f} %"}, PRIORITY_LOW))
    recs.append(Recommendation("analysis.crop_growth.rec.local_review", {}, PRIORITY_LOW))
    weather_name = " + ".join(main.weather_providers)
    sources = SOURCES_BASE + (DataSource(weather_name, "analysis.var.weather", "1 d"),)
    params = {"crop": crop_key, "variety": main.variety_name, "sowing": main.sowing.isoformat(),
              "mode": "analysis.crop_growth.mode.irrigated" if main.irrigated
              else "analysis.crop_growth.mode.rainfed",
              "yield": f"{yield_t:.1f}"}
    summary = ("analysis.crop_growth.summary_in_season" if main.in_season
               else "analysis.crop_growth.summary_next")
    return _result(field, sources, series, frames, metrics, summary, params, recs)
