"""PLACEHOLDER analyses: every number here is made up.

They only exist so the UI can be built before the algorithms and the data
access are ready. Each run_* function will be replaced by a real one that
reads its sources through fieldshift.api.get_site_data (ERA5-Land, GPM
IMERG, WaPOR, SMAP, SoilGrids...) and computes the result. The made-up
values follow the seasons of the southern hemisphere and depend on the field
(same field, same numbers), so the screens look plausible.
"""

import hashlib
import math
import random

from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW,
    PRIORITY_MEDIUM, AnalysisResult, DataSource, MapFrames, Metric, Recommendation, Series)

# months covered by every placeholder result
PLACEHOLDER_MONTHS = tuple(f"{year}-{month:02d}" for year in (2024, 2025) for month in range(1, 13))
# cells per side of the map grid
GRID_SIZE = 8

VEGETATION_SOURCES = (
    DataSource("Sentinel-2 L2A", "analysis.var.ndvi", "10 m · 5 d"),
    DataSource("MODIS MOD13Q1", "analysis.var.ndvi", "250 m · 16 d"),
)
FROST_SOURCES = (DataSource("ERA5-Land", "analysis.var.tmin", "9 km · 1 h"),)
WATER_SOURCES = (
    DataSource("GPM IMERG", "analysis.var.rain", "10 km · 30 min"),
    DataSource("WaPOR", "analysis.var.et", "300 m · 10 d"),
    DataSource("SMAP", "analysis.var.soil_moisture", "9 km · 1 d"),
)
HEAT_SOURCES = (DataSource("ERA5-Land", "analysis.var.tmax", "9 km · 1 h"),)
ROTATION_SOURCES = (
    DataSource("Field Shift", "analysis.var.previous_results", ""),
    DataSource("SoilGrids", "analysis.var.soil", "250 m"),
    DataSource("FAO GAEZ", "analysis.var.crop_suitability", "1 km"),
)


# (Field field, str analysis_id)
# random generator that always gives the same numbers for this field
def _rng(field, analysis_id):
    seed = f"{analysis_id}:{field.name}:{field.vertices[0][0]:.4f}:{field.vertices[0][1]:.4f}"
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))


# (str date, float lat)
# 0 in mid-winter, 1 in mid-summer, for the hemisphere of lat
def _summer(date, lat):
    month = int(date[5:7])
    peak = 1 if lat < 0 else 7                   # January in the south
    return (1 + math.cos(2 * math.pi * (month - peak) / 12)) / 2


def _center(field):
    return (sum(v[0] for v in field.vertices) / len(field.vertices),
            sum(v[1] for v in field.vertices) / len(field.vertices))


# (Field field, str analysis_id, callable value_at, float spread, str label_key,
#  str unit, float low, float high, str palette, int decimals)
# made-up series plus map frames: value_at(date, rng) gives the monthly value;
# every map cell varies around it by up to spread
def _series_and_frames(field, analysis_id, value_at, spread, label_key, unit, low, high,
                       palette, decimals=1):
    rng = _rng(field, analysis_id)
    values = tuple(round(value_at(date, rng), decimals) for date in PLACEHOLDER_MONTHS)
    # a fixed pattern of better and worse zones inside the field
    pattern = [[rng.uniform(-1, 1) for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    grids = tuple(
        tuple(tuple(round(min(high, max(low, value + spread * cell)), decimals) for cell in row)
              for row in pattern)
        for value in values)
    return (Series(label_key, unit, PLACEHOLDER_MONTHS, values),
            MapFrames(label_key, unit, PLACEHOLDER_MONTHS, grids, low, high, palette))


def _month_of(series, pick):
    index = series.values.index(pick(series.values))
    return int(series.dates[index][5:7])


# (Field field)
# PLACEHOLDER: vegetation vigour (NDVI) over two years
def run_vegetation(field):
    lat = _center(field)[1]
    trend = _rng(field, "vegetation-trend").uniform(-0.06, 0.06)
    series, frames = _series_and_frames(
        field, "vegetation",
        lambda d, r: 0.25 + 0.5 * _summer(d, lat) + trend * (d >= "2025") + r.uniform(-0.04, 0.04),
        0.12, "analysis.var.ndvi", "", 0.0, 1.0, "vegetation", 2)
    mean = sum(series.values) / len(series.values)
    change = 100 * (sum(series.values[12:]) - sum(series.values[:12])) / sum(series.values[:12])
    weak_cell = min(min(row) for row in frames.grids[-1])
    metrics = (
        Metric("analysis.vegetation.m.mean", f"{mean:.2f}",
               LEVEL_GOOD if mean > 0.5 else LEVEL_WARNING),
        Metric("analysis.vegetation.m.peak", f"month.{_month_of(series, max)}"),
        Metric("analysis.vegetation.m.change", f"{change:+.0f} %",
               LEVEL_GOOD if change >= 0 else LEVEL_BAD),
    )
    recs = [Recommendation("analysis.vegetation.r.zones", {"value": f"{weak_cell:.2f}"},
                           PRIORITY_HIGH if weak_cell < 0.3 else PRIORITY_MEDIUM),
            Recommendation("analysis.vegetation.r.soil_test", {}, PRIORITY_MEDIUM),
            Recommendation("analysis.vegetation.r.cover", {}, PRIORITY_LOW)]
    if change < 0:
        recs.insert(0, Recommendation("analysis.vegetation.r.decline",
                                      {"change": f"{change:.0f}"}, PRIORITY_HIGH))
    return AnalysisResult("vegetation", field.name, VEGETATION_SOURCES, series, frames, metrics,
                          "analysis.vegetation.summary", {"mean": f"{mean:.2f}"}, tuple(recs))


# (Field field)
# PLACEHOLDER: minimum temperature and frost risk
def run_frost(field):
    lat = _center(field)[1]
    series, frames = _series_and_frames(
        field, "frost", lambda d, r: -2.5 + 12 * _summer(d, lat) + r.uniform(-1.5, 1.5),
        1.5, "analysis.var.tmin", "°C", -8.0, 16.0, "temperature")
    frost_months = [d for d, v in zip(series.dates, series.values) if v < 2]
    frost_days = sum(max(0, round((2 - v) * 4)) for v in series.values[12:])
    worst = _month_of(series, min)
    level = LEVEL_BAD if frost_days > 20 else LEVEL_WARNING if frost_days > 5 else LEVEL_GOOD
    last_month = max((int(d[5:7]) for d in frost_months), default=worst)
    metrics = (
        Metric("analysis.frost.m.days", str(frost_days), level),
        Metric("analysis.frost.m.worst", f"month.{worst}"),
        Metric("analysis.frost.m.min", f"{min(series.values):.1f} °C", level),
    )
    recs = (
        Recommendation("analysis.frost.r.sowing", {"month": f"month.{last_month % 12 + 1}"},
                       PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM),
        Recommendation("analysis.frost.r.sensitive", {}, PRIORITY_MEDIUM),
        Recommendation("analysis.frost.r.protection", {}, PRIORITY_LOW),
    )
    return AnalysisResult("frost", field.name, FROST_SOURCES, series, frames, metrics,
                          "analysis.frost.summary", {"days": str(frost_days),
                                                     "month": f"month.{worst}"}, recs)


# (Field field)
# PLACEHOLDER: monthly water balance (rain minus evapotranspiration)
def run_water(field):
    lat = _center(field)[1]
    series, frames = _series_and_frames(
        field, "water", lambda d, r: 70 - 160 * _summer(d, lat) + r.uniform(-20, 20),
        25, "analysis.var.balance", "mm", -150.0, 150.0, "water", 0)
    deficit = -sum(v for v in series.values[12:] if v < 0)
    dry = sum(1 for v in series.values[12:] if v < 0)
    level = LEVEL_BAD if deficit > 600 else LEVEL_WARNING if deficit > 250 else LEVEL_GOOD
    metrics = (
        Metric("analysis.water.m.deficit", f"{deficit:.0f} mm", level),
        Metric("analysis.water.m.dry", str(dry), level),
        Metric("analysis.water.m.driest", f"month.{_month_of(series, min)}"),
    )
    recs = (
        Recommendation("analysis.water.r.irrigation", {"mm": f"{deficit:.0f}"},
                       PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM),
        Recommendation("analysis.water.r.crops", {}, PRIORITY_MEDIUM),
        Recommendation("analysis.water.r.mulch", {}, PRIORITY_LOW),
    )
    return AnalysisResult("water", field.name, WATER_SOURCES, series, frames, metrics,
                          "analysis.water.summary", {"mm": f"{deficit:.0f}", "months": str(dry)},
                          recs)


# (Field field)
# PLACEHOLDER: maximum temperature and heat stress
def run_heat(field):
    lat = _center(field)[1]
    series, frames = _series_and_frames(
        field, "heat", lambda d, r: 14 + 18 * _summer(d, lat) + r.uniform(-2, 2.5),
        2.0, "analysis.var.tmax", "°C", 5.0, 40.0, "temperature")
    hot_days = sum(max(0, round((v - 29) * 5)) for v in series.values[12:])
    level = LEVEL_BAD if hot_days > 30 else LEVEL_WARNING if hot_days > 8 else LEVEL_GOOD
    hottest = _month_of(series, max)
    metrics = (
        Metric("analysis.heat.m.days", str(hot_days), level),
        Metric("analysis.heat.m.hottest", f"month.{hottest}"),
        Metric("analysis.heat.m.max", f"{max(series.values):.1f} °C", level),
    )
    recs = (
        Recommendation("analysis.heat.r.flowering", {"month": f"month.{hottest}"},
                       PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM),
        Recommendation("analysis.heat.r.irrigation_time", {}, PRIORITY_MEDIUM),
        Recommendation("analysis.heat.r.varieties", {}, PRIORITY_LOW),
    )
    return AnalysisResult("heat", field.name, HEAT_SOURCES, series, frames, metrics,
                          "analysis.heat.summary", {"days": str(hot_days)}, recs)


# crops the placeholder rotation chooses from (i18n keys crop.<name>)
_CROPS = ("wheat", "oat", "lupin", "chickpea", "maize", "potato", "canola", "pea")


# (Field field)
# PLACEHOLDER: suggested crop rotation for the next three seasons
def run_rotation(field):
    lat = _center(field)[1]
    rng = _rng(field, "rotation-crops")
    cereals, legumes, others = ["wheat", "oat", "maize"], ["lupin", "chickpea", "pea"], ["potato", "canola"]
    plan = (rng.choice(cereals), rng.choice(legumes), rng.choice(others))
    series, frames = _series_and_frames(
        field, "rotation", lambda d, r: 55 + 25 * _summer(d, lat) + r.uniform(-6, 6),
        12, "analysis.var.suitability", "%", 0.0, 100.0, "suitability", 0)
    score = round(sum(series.values[12:]) / 12)
    metrics = (
        Metric("analysis.rotation.m.plan",
               " → ".join(f"crop.{c}" for c in plan), LEVEL_NEUTRAL),
        Metric("analysis.rotation.m.score", f"{score} %",
               LEVEL_GOOD if score >= 65 else LEVEL_WARNING),
        Metric("analysis.rotation.m.benefit", f"+{rng.randint(6, 18)} %", LEVEL_GOOD),
    )
    recs = (
        Recommendation("analysis.rotation.r.season1", {"crop": f"crop.{plan[0]}",
                                                       "month": "month.4"}, PRIORITY_HIGH),
        Recommendation("analysis.rotation.r.season2", {"crop": f"crop.{plan[1]}"}, PRIORITY_MEDIUM),
        Recommendation("analysis.rotation.r.season3", {"crop": f"crop.{plan[2]}"}, PRIORITY_MEDIUM),
        Recommendation("analysis.rotation.r.avoid", {"crop": f"crop.{plan[0]}"}, PRIORITY_LOW),
    )
    return AnalysisResult("rotation", field.name, ROTATION_SOURCES, series, frames, metrics,
                          "analysis.rotation.summary",
                          {"first": f"crop.{plan[0]}", "score": str(score)}, recs)
