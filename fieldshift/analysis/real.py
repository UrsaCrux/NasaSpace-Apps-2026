"""The analyses with real data: vegetation, frost, water, heat and rotation.

Data comes through fieldshift.analysis.sources (NASA POWER, FAO WaPOR,
Copernicus DEM, Open-Meteo, FAO EcoCrop). Each run_* returns an
AnalysisResult over the last two years (24 complete months); when a source
cannot be reached the result says so instead of showing made-up numbers.
"""

import calendar
import datetime as dt

from fieldshift import crops
from fieldshift.analysis import sources
from fieldshift.analysis.models import (
    LEVEL_BAD, LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW,
    PRIORITY_MEDIUM, AnalysisResult, DataSource, MapFrames, Metric, Recommendation, Series)

# temperature change with height (°C per metre) used to spread the 0.5° NASA
# POWER temperatures over the field's relief
LAPSE_RATE = -0.0065
# heat-stress threshold when the field's crop has no EcoCrop limit (°C)
DEFAULT_HEAT_C = 32.0
MONTH_KEYS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

VEGETATION_SOURCES = (DataSource("FAO WaPOR v3", "analysis.var.npp", "300 m · monthly"),)
FROST_SOURCES = (DataSource("NASA POWER", "analysis.var.tmin", "0.5° · daily"),
                 DataSource("Copernicus DEM", "analysis.var.elevation", "30 m"),
                 DataSource("Open-Meteo", "analysis.var.forecast", "7 d"))
WATER_SOURCES = (DataSource("NASA POWER", "analysis.var.rain", "0.5° · daily"),
                 DataSource("FAO WaPOR v3", "analysis.var.et", "300 m · monthly"))
HEAT_SOURCES = (DataSource("NASA POWER", "analysis.var.tmax", "0.5° · daily"),
                DataSource("Copernicus DEM", "analysis.var.elevation", "30 m"),
                DataSource("FAO EcoCrop", "analysis.var.crop_limits", ""))
ROTATION_SOURCES = (DataSource("NASA POWER", "analysis.var.climate_normals", "2001-2025"),
                    DataSource("FAO EcoCrop", "analysis.var.crop_limits", ""),
                    DataSource("SoilGrids", "analysis.var.soil", "250 m"))


# -- shared helpers ---------------------------------------------------------

def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _month_of(date):
    return f"{date:%Y-%m}"


def _value(field, key):
    return (((field.data or {}).get(key)) or {}).get("value")


# (str analysis_id, Field field, tuple sources, Exception error)
# a result that says the data could not be obtained (no made-up numbers)
def unavailable(analysis_id, field, source_list, error):
    return AnalysisResult(
        analysis_id, field.name, source_list, None, None,
        (Metric("analysis.common.m.status", "analysis.common.status.unavailable", LEVEL_BAD),),
        "analysis.common.summary_unavailable", {"error": str(error)[:200]},
        (Recommendation("analysis.common.r.retry", {}, PRIORITY_HIGH),), placeholder=False)


# (list grids) -> every cell filled (None -> the grid's mean), and (low, high)
def _filled(grids):
    out = []
    for grid in grids:
        m = _mean([v for row in grid for v in row]) or 0.0
        out.append(tuple(tuple(round(v if v is not None else m, 2) for v in row) for row in grid))
    values = [v for g in out for row in g for v in row]
    low, high = min(values), max(values)
    if high - low < 1e-6:
        high = low + 1.0
    return tuple(out), round(low, 2), round(high, 2)


# (float value, list relief) -> the value spread over the field's relief
def _relief_grid(value, relief):
    if relief is None:
        return [[value] * sources.GRID for _ in range(sources.GRID)]
    mean_z = _mean([v for row in relief for v in row])
    return [[value + LAPSE_RATE * (z - mean_z) if z is not None else value for z in row]
            for row in relief]


def _period(months):
    first = dt.date(int(months[0][:4]), int(months[0][5:]), 1)
    y, m = int(months[-1][:4]), int(months[-1][5:])
    last = dt.date(y, m, calendar.monthrange(y, m)[1])
    return first, min(last, sources.today() - dt.timedelta(days=1))


def _daily(field, months):
    lon, lat = sources.center(field)
    start, end = _period(months)
    return sources.power_daily(lon, lat, start, end)


def _monthly(daily, months, how):
    out = {}
    for month in months:
        values = [v for d, v in daily.items() if _month_of(d) == month]
        if values:
            out[month] = how(values)
    return out


# -- vegetation -------------------------------------------------------------

# (Field field)
# vegetation productivity: WaPOR net primary production month by month over
# the field, with its weaker zones (real 300 m pixels)
def run_vegetation(field):
    months = sources.last_months()
    try:
        grids = sources.wapor_grids("L1-NPP-M", field, months)
    except Exception as exc:
        return unavailable("vegetation", field, VEGETATION_SOURCES, exc)
    months = [m for m in months if grids.get(m) is not None]
    if len(months) < 3:
        return unavailable("vegetation", field, VEGETATION_SOURCES, "no WaPOR data here")
    raw = [grids[m] for m in months]
    values = tuple(round(_mean([v for row in g for v in row]), 1) for g in raw)
    filled, low, high = _filled(raw)
    series = Series("analysis.var.npp", "gC/m²", tuple(months), values)
    frames = MapFrames("analysis.var.npp", "gC/m²", tuple(months), filled, low, high, "vegetation")
    year = values[-12:]
    before = values[:-12]
    mean = sum(year) / len(year)
    change = 100 * (sum(year) / len(year) - _mean(before)) / _mean(before) if before and \
        _mean(before) else 0.0
    peak = int(months[values.index(max(values))][5:])
    last = [v for row in raw[-1] for v in row if v is not None]
    weak = 100 * (min(last) - _mean(last)) / _mean(last) if last and _mean(last) else 0.0
    metrics = (
        Metric("analysis.vegetation.m.mean", f"{mean:.0f} gC/m²",
               LEVEL_GOOD if mean >= 40 else LEVEL_WARNING),
        Metric("analysis.vegetation.m.peak", f"month.{peak}"),
        Metric("analysis.vegetation.m.change", f"{change:+.0f} %",
               LEVEL_GOOD if change >= -5 else LEVEL_BAD),
        Metric("analysis.vegetation.m.annual", f"{sum(year) * 10 / 1000 * 2.2:.1f} t/ha"),
    )
    recs = [Recommendation("analysis.vegetation.r.zones", {"value": f"{weak:.0f}"},
                           PRIORITY_HIGH if weak < -20 else PRIORITY_MEDIUM),
            Recommendation("analysis.vegetation.r.soil_test", {}, PRIORITY_MEDIUM),
            Recommendation("analysis.vegetation.r.cover", {}, PRIORITY_LOW)]
    if change < -10:
        recs.insert(0, Recommendation("analysis.vegetation.r.decline",
                                      {"change": f"{change:.0f}"}, PRIORITY_HIGH))
    return AnalysisResult("vegetation", field.name, VEGETATION_SOURCES, series, frames, metrics,
                          "analysis.vegetation.summary", {"mean": f"{mean:.0f}"}, tuple(recs),
                          placeholder=False)


# -- frost --------------------------------------------------------------------

def _season_order(by_month):
    """Calendar months starting after the warmest one (a cold season in order)."""
    warmest = max(range(1, 13), key=lambda m: by_month.get(m, -99))
    return [(warmest + i - 1) % 12 + 1 for i in range(1, 13)]


# (Field field)
# frost risk: coldest temperature of each month (NASA POWER), spread over
# the field's relief (DEM), frost days, and the coming week's frosts
def run_frost(field):
    months = sources.last_months()
    try:
        daily = _daily(field, months)["T2M_MIN"]
    except Exception as exc:
        return unavailable("frost", field, FROST_SOURCES, exc)
    lowest = _monthly(daily, months, min)
    months = [m for m in months if m in lowest]
    if len(months) < 3:
        return unavailable("frost", field, FROST_SOURCES, "no temperature data")
    relief = _safe(lambda: sources.dem_grid(field))
    values = tuple(round(lowest[m], 1) for m in months)
    filled, low, high = _filled([_relief_grid(v, relief) for v in values])
    series = Series("analysis.var.tmin", "°C", tuple(months), values)
    frames = MapFrames("analysis.var.tmin", "°C", tuple(months), filled, low, high, "temperature")
    recent = set(months[-12:])
    frost_days = sum(1 for d, v in daily.items() if _month_of(d) in recent and v <= 0)
    per_month = {}
    for d, v in daily.items():
        if _month_of(d) in recent and v <= 0:
            per_month[d.month] = per_month.get(d.month, 0) + 1
    worst = int(months[values.index(min(values))][5:])
    level = LEVEL_BAD if frost_days > 20 else LEVEL_WARNING if frost_days > 3 else LEVEL_GOOD
    lon, lat = sources.center(field)
    upcoming = _safe(lambda: sources.forecast(lon, lat))
    coming = len(upcoming.frost_days()) if upcoming is not None else None
    climate = _safe(lambda: sources.power_climatology(lon, lat))
    metrics = [
        Metric("analysis.frost.m.days", str(frost_days), level),
        Metric("analysis.frost.m.worst", f"month.{worst}"),
        Metric("analysis.frost.m.min", f"{min(values[-12:]):.1f} °C", level),
        Metric("analysis.frost.m.forecast", "—" if coming is None else str(coming),
               LEVEL_BAD if coming else LEVEL_GOOD if coming == 0 else LEVEL_NEUTRAL),
    ]
    if climate and "FROST_DAYS" in climate:
        metrics.append(Metric("analysis.frost.m.typical",
                              f"{climate['FROST_DAYS'].get('ANN', 0):.0f}"))
    mean_min = {int(m[5:]): v for m, v in zip(months, values)}
    order = _season_order(mean_min)
    frost_months = [m for m in order if per_month.get(m)]
    if frost_months:                               # sow after the season's last frost month
        first = Recommendation("analysis.frost.r.sowing",
                               {"month": f"month.{frost_months[-1] % 12 + 1}"},
                               PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM)
    else:
        first = Recommendation("analysis.frost.r.no_frost", {}, PRIORITY_LOW)
    recs = [first,
            Recommendation("analysis.frost.r.sensitive", {}, PRIORITY_MEDIUM),
            Recommendation("analysis.frost.r.protection", {}, PRIORITY_LOW)]
    if coming:
        recs.insert(0, Recommendation("analysis.frost.r.coming", {"days": str(coming)},
                                      PRIORITY_HIGH))
    return AnalysisResult("frost", field.name, FROST_SOURCES, series, frames, tuple(metrics),
                          "analysis.frost.summary", {"days": str(frost_days),
                                                     "month": f"month.{worst}"}, tuple(recs),
                          placeholder=False)


def _safe(compute):
    try:
        return compute()
    except Exception:
        return None


# -- water --------------------------------------------------------------------

# (Field field)
# water balance: monthly rain (NASA POWER) minus actual evapotranspiration
# (WaPOR, per 300 m pixel); negative months are a deficit
def run_water(field):
    months = sources.last_months()
    try:
        rain = _monthly(_daily(field, months)["PRECTOTCORR"], months, sum)
        et = sources.wapor_grids("L1-AETI-M", field, months)
    except Exception as exc:
        return unavailable("water", field, WATER_SOURCES, exc)
    months = [m for m in months if m in rain and et.get(m) is not None]
    if len(months) < 3:
        return unavailable("water", field, WATER_SOURCES, "no rain or ET data")
    grids = [[[rain[m] - v if v is not None else None for v in row] for row in et[m]]
             for m in months]
    values = tuple(round(_mean([v for row in g for v in row]), 0) for g in grids)
    filled, low, high = _filled(grids)
    series = Series("analysis.var.balance", "mm", tuple(months), values)
    frames = MapFrames("analysis.var.balance", "mm", tuple(months), filled, low, high, "water")
    year = values[-12:]
    deficit = -sum(v for v in year if v < 0)
    dry = sum(1 for v in year if v < 0)
    yearly_rain = sum(rain[m] for m in months[-12:])
    level = LEVEL_BAD if deficit > 600 else LEVEL_WARNING if deficit > 250 else LEVEL_GOOD
    driest = int(months[values.index(min(values))][5:])
    metrics = (
        Metric("analysis.water.m.deficit", f"{deficit:.0f} mm", level),
        Metric("analysis.water.m.dry", str(dry), level),
        Metric("analysis.water.m.driest", f"month.{driest}"),
        Metric("analysis.water.m.rain", f"{yearly_rain:.0f} mm"),
    )
    irrigated = bool(_value(field, "irrigated"))
    recs = (
        Recommendation("analysis.water.r.irrigated" if irrigated else "analysis.water.r.irrigation",
                       {"mm": f"{deficit:.0f}"},
                       PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM),
        Recommendation("analysis.water.r.crops", {}, PRIORITY_MEDIUM),
        Recommendation("analysis.water.r.mulch", {}, PRIORITY_LOW),
    )
    return AnalysisResult("water", field.name, WATER_SOURCES, series, frames, metrics,
                          "analysis.water.summary", {"mm": f"{deficit:.0f}", "months": str(dry)},
                          recs, placeholder=False)


# -- heat ---------------------------------------------------------------------

# (Field field)
# heat stress: hottest temperature of each month (NASA POWER) over the
# field's relief, and the days above the crop's limit (EcoCrop) or 32 °C
def run_heat(field):
    months = sources.last_months()
    try:
        daily = _daily(field, months)["T2M_MAX"]
    except Exception as exc:
        return unavailable("heat", field, HEAT_SOURCES, exc)
    highest = _monthly(daily, months, max)
    months = [m for m in months if m in highest]
    if len(months) < 3:
        return unavailable("heat", field, HEAT_SOURCES, "no temperature data")
    crop = _safe(lambda: sources.crop_requirements(field))
    # stress starts above the crop's optimal range (the absolute maximum is
    # what it survives, not where it stops growing well)
    limit = crop.temperature.optimal_max if crop and crop.temperature.optimal_max else None
    threshold = limit or DEFAULT_HEAT_C
    relief = _safe(lambda: sources.dem_grid(field))
    values = tuple(round(highest[m], 1) for m in months)
    filled, low, high = _filled([_relief_grid(v, relief) for v in values])
    series = Series("analysis.var.tmax", "°C", tuple(months), values)
    frames = MapFrames("analysis.var.tmax", "°C", tuple(months), filled, low, high, "temperature")
    recent = set(months[-12:])
    hot_days = sum(1 for d, v in daily.items() if _month_of(d) in recent and v >= threshold)
    level = LEVEL_BAD if hot_days > 30 else LEVEL_WARNING if hot_days > 8 else LEVEL_GOOD
    hottest = int(months[values.index(max(values))][5:])
    metrics = (
        Metric("analysis.heat.m.days", str(hot_days), level),
        Metric("analysis.heat.m.threshold", f"{threshold:.0f} °C"
               + (" (EcoCrop)" if limit else "")),
        Metric("analysis.heat.m.hottest", f"month.{hottest}"),
        Metric("analysis.heat.m.max", f"{max(values[-12:]):.1f} °C", level),
    )
    recs = [Recommendation("analysis.heat.r.flowering", {"month": f"month.{hottest}"},
                           PRIORITY_HIGH if level == LEVEL_BAD else PRIORITY_MEDIUM),
            Recommendation("analysis.heat.r.irrigation_time", {}, PRIORITY_MEDIUM),
            Recommendation("analysis.heat.r.varieties", {}, PRIORITY_LOW)]
    if not limit:
        recs.append(Recommendation("analysis.heat.r.choose_crop", {}, PRIORITY_LOW))
    return AnalysisResult("heat", field.name, HEAT_SOURCES, series, frames, metrics,
                          "analysis.heat.summary", {"days": str(hot_days),
                                                    "threshold": f"{threshold:.0f}"},
                          tuple(recs), placeholder=False)


# -- rotation -----------------------------------------------------------------

# catalogue crops considered for a rotation, by role
CEREALS = ("wheat", "barley", "oat", "maize", "quinoa", "rice")
LEGUMES = ("lupin", "chickpea", "lentil", "pea", "bean")
SOIL_BUILDERS = ("alfalfa", "red_clover", "vetch")
BREAK_CROPS = ("canola", "sunflower", "potato", "sugar_beet", "onion", "garlic", "pumpkin")
TEXTURE_WEIGHT = {"light": ("sand", "loamy_sand", "sandy_loam"),
                  "heavy": ("clay", "silty_clay", "sandy_clay")}


def _ramp(value, rng):
    """1 inside the optimal range, falling to 0 at the absolute limits."""
    lo, hi, alo, ahi = rng.optimal_min, rng.optimal_max, rng.absolute_min, rng.absolute_max
    if value is None or lo is None or hi is None:
        return 1.0
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return max(0.0, (value - alo) / (lo - alo)) if alo is not None and alo < lo else 0.3
    return max(0.0, (ahi - value) / (ahi - hi)) if ahi is not None and ahi > hi else 0.3


def _texture_term(texture):
    for term, classes in TEXTURE_WEIGHT.items():
        if texture in classes:
            return term
    return "medium"


# (CropInfo crop, dict field_climate, dict soil, bool irrigated)
# (score 0..100, best sowing month) of a crop for this field and climate
def crop_score(crop, climate, soil, irrigated):
    temps, rain_year, extreme_min = climate["temps"], climate["rain"], climate["min"]
    # months the crop is in the field: from its shortest cycle (EcoCrop's
    # longest is often a whole year for perennial uses)
    cycle = min(8, max(3, round((crop.crop_cycle_min or 120) * 1.3 / 30)))
    rain_months = climate.get("rain_months") or [1.0] * 12
    mid = None
    if crop.temperature.optimal_min is not None and crop.temperature.optimal_max is not None:
        mid = (crop.temperature.optimal_min + crop.temperature.optimal_max) / 2
    best, best_month, best_rank = 0.0, 1, -1.0
    for start in range(1, 13):
        months = [(start - 1 + i) % 12 for i in range(min(cycle, 12))]
        mean_t = sum(temps[m] for m in months) / len(months)
        t = _ramp(mean_t, crop.temperature)
        coldest = min(extreme_min[m] for m in months)
        kill = crop.killing_temp_early_growth
        frost = 0.4 if kill is not None and coldest < kill else 1.0
        score = t * frost
        # among equally good windows: temperatures nearest the crop's optimum,
        # and (rain-fed) the window that catches most of the year's rain
        rank = score - (abs(mean_t - mid) / 100 if mid is not None else 0)
        if not irrigated:
            rank += 0.2 * sum(rain_months[m] for m in months) / (sum(rain_months) or 1)
        if rank > best_rank:
            best, best_month, best_rank = score, start, rank
    rain = 1.0 if irrigated else _ramp(rain_year, crop.rainfall)
    ph = _ramp(soil.get("ph"), crop.ph)
    term = _texture_term(soil.get("texture"))
    texture = 1.0
    if soil.get("texture") and crop.soil_texture and any(crop.soil_texture.values()):
        texture = (1.0 if term in crop.soil_texture.get("optimal", "") else
                   0.7 if term in crop.soil_texture.get("absolute", "") else 0.4)
    return round(100 * best * rain * ph * texture), best_month


def _field_climate(field):
    lon, lat = sources.center(field)
    c = sources.power_climatology(lon, lat)
    temps = [c["T2M"][k] for k in MONTH_KEYS]
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    rain_months = [c["PRECTOTCORR"][k] * n for k, n in zip(MONTH_KEYS, days)]
    return {"temps": temps, "rain": sum(rain_months), "rain_months": rain_months,
            "min": [c["T2M_MIN"][k] for k in MONTH_KEYS]}


# (Field field)
# crop rotation: scores the catalogue's field crops against the field's
# climate normals, soil pH and texture with their EcoCrop requirements, and
# compares three strategies: the current crop every season, a diversified
# cereal / legume / break-crop rotation and a soil-building one
def run_rotation(field):
    from concurrent.futures import ThreadPoolExecutor
    from fieldshift.crops import rotation
    from fieldshift.fields.records import past_crops
    try:
        climate = _field_climate(field)
    except Exception as exc:
        return unavailable("rotation", field, ROTATION_SOURCES, exc)
    candidates = tuple(dict.fromkeys(CEREALS + LEGUMES + SOIL_BUILDERS + BREAK_CROPS
                                     + rotation.COVER_GRASSES))
    with ThreadPoolExecutor(max_workers=8) as pool:
        infos = dict(zip(candidates, pool.map(
            lambda c: sources.crop_requirements_of(crops.ecocrop_name(f"{c}.v1")), candidates)))
    soil = {"ph": _value(field, "ph"), "texture": _value(field, "soil_texture")}
    irrigated = bool(_value(field, "irrigated"))
    scores = {c: crop_score(i, climate, soil, irrigated) for c, i in infos.items() if i}
    if not scores:
        return unavailable("rotation", field, ROTATION_SOURCES, "no EcoCrop data")

    # the current crop: its id, data sheet, score and role
    current_value = _value(field, "crop")
    variety = crops.variety_by_id(current_value) if current_value else None
    current = variety.crop if variety else None
    current_info = _safe(lambda: sources.crop_requirements(field))
    current_score = crop_score(current_info, climate, soil, irrigated) if current_info else None
    current_name = f"crop.{current}" if current else \
        ((field.data or {}).get("crop") or {}).get("name", "")
    today = sources.today()
    # families grown lately (the current crop and the farmer's sowing records)
    recent = ([current] if current else []) + past_crops(field.records, today.isoformat())
    recent_families = {rotation.family_of(c, infos.get(c)) for c in recent} - {""}
    if current_info is not None and current_info.family:
        recent_families.add(current_info.family)

    def best(group, avoid_families=(), exclude=()):
        ranked = sorted((c for c in group if c in scores and c not in exclude
                         and rotation.family_of(c, infos.get(c)) not in avoid_families),
                        key=lambda c: -scores[c][0])
        return ranked[0] if ranked else None

    def monthly(info):
        # month-by-month temperature suitability of a crop, next 12 months (%)
        dates, values = [], []
        for i in range(12):
            m = (today.month + i) % 12 + 1
            y = today.year + (today.month + i) // 12
            dates.append(f"{y}-{m:02d}")
            values.append(round(100 * min(1.0, _ramp(climate["temps"][m - 1], info.temperature))))
        return dates, values

    recs, metrics = [], []
    if current and rotation.is_perennial(current, current_info) or \
            (not current and current_info is not None and rotation.is_perennial("", current_info)):
        # perennial crop (vines, orchards...): it stays for years, so there is
        # no rotation and no crop to harvest in between; only cover crops
        # sown between the rows and cut, never harvested. no monthly chart: a
        # dormant perennial in winter is not "unsuitable"
        legume = best(rotation.COVER_LEGUMES)
        grass = best(rotation.COVER_GRASSES)
        with_water = crop_score(current_info, climate, soil, True)[0] if current_info else None
        rainfed = current_score[0] if current_score else None
        chart_info = None
        summary, summary_params = "analysis.rotation.summary_perennial", {"crop": current_name}
        metrics = [
            Metric("analysis.rotation.m.current_type", "analysis.rotation.perennial"),
            Metric("analysis.rotation.m.climate_irrigated",
                   f"{with_water} %" if with_water is not None else "—",
                   LEVEL_NEUTRAL if with_water is None else
                   LEVEL_GOOD if with_water >= 65 else LEVEL_WARNING),
            Metric("analysis.rotation.m.climate_rainfed",
                   f"{rainfed} %" if rainfed is not None else "—",
                   LEVEL_NEUTRAL if rainfed is None else
                   LEVEL_GOOD if rainfed >= 65 else LEVEL_WARNING),
            Metric("analysis.rotation.m.covers", " + ".join(
                f"crop.{c}" for c in (legume, grass) if c) or "—"),
        ]
        recs.append(Recommendation("analysis.rotation.r.perennial", {"crop": current_name},
                                   PRIORITY_HIGH))
        if legume:
            recs.append(Recommendation("analysis.rotation.r.cover_legume",
                                       {"crop": f"crop.{legume}"}, PRIORITY_MEDIUM))
        if grass:
            recs.append(Recommendation("analysis.rotation.r.cover_grass",
                                       {"crop": f"crop.{grass}"}, PRIORITY_LOW))
        if rainfed is not None and with_water is not None and with_water - rainfed >= 30:
            recs.append(Recommendation("analysis.rotation.r.perennial_water",
                                       {"crop": current_name, "mm": f"{climate['rain']:.0f}"},
                                       PRIORITY_MEDIUM))
    else:
        # annual crop (or none): the next seasons start from the current crop,
        # never two of one family in a row, alternating the roles
        role = (rotation.CEREAL if current in CEREALS else rotation.LEGUME if current in LEGUMES
                else rotation.BREAK if current else None)
        groups = {rotation.CEREAL: CEREALS, rotation.LEGUME: LEGUMES + SOIL_BUILDERS,
                  rotation.BREAK: BREAK_CROPS}
        reasons = {rotation.CEREAL: "analysis.rotation.why.cereal",
                   rotation.LEGUME: "analysis.rotation.why.legume",
                   rotation.BREAK: "analysis.rotation.why.break"}
        plan, roles, used = [], [], set(recent_families)
        for next_role in (rotation.NEXT_ROLE[role], rotation.THIRD_ROLE[role],
                          rotation.NEXT_ROLE[rotation.THIRD_ROLE[role]]):
            crop = best(groups[next_role], used, plan) or best(groups[next_role], (), plan)
            if crop:
                plan.append(crop)
                roles.append(next_role)
                used = {rotation.family_of(crop, infos.get(crop))}
        if not plan:
            return unavailable("rotation", field, ROTATION_SOURCES, "no suitable crop")
        plan_score = round(sum(scores[c][0] for c in plan) / len(plan))
        chart_name, chart_info = f"crop.{plan[0]}", infos[plan[0]]
        if not current_name:
            recs.append(Recommendation("analysis.rotation.r.no_crop", {}, PRIORITY_MEDIUM))
        summary = "analysis.rotation.summary_after" if current_name else "analysis.rotation.summary"
        summary_params = {"first": f"crop.{plan[0]}", "score": str(plan_score),
                          "crop": current_name}
        metrics = [
            Metric("analysis.rotation.m.current_type",
                   "analysis.rotation.annual" if current_name else "—"),
            Metric("analysis.rotation.m.plan_from", " → ".join(
                ([current_name] if current_name else []) + [f"crop.{c}" for c in plan])),
            Metric("analysis.rotation.m.score", f"{plan_score} %",
                   LEVEL_GOOD if plan_score >= 65 else LEVEL_WARNING),
            Metric("analysis.rotation.m.current",
                   f"{current_score[0]} %" if current_score else "—",
                   LEVEL_NEUTRAL if not current_score else
                   LEVEL_GOOD if current_score[0] >= 65 else LEVEL_WARNING),
            Metric("analysis.rotation.m.sowing", f"month.{scores[plan[0]][1]}"),
        ]
        for i, (crop, crop_role) in enumerate(zip(plan, roles), start=1):
            recs.append(Recommendation(
                "analysis.rotation.r.season", {
                    "n": str(i), "crop": f"crop.{crop}", "why": reasons[crop_role],
                    "score": str(scores[crop][0]),
                    "month": f"month.{scores[crop][1]}"},
                PRIORITY_HIGH if i == 1 else PRIORITY_MEDIUM))
        if current_name:
            recs.append(Recommendation("analysis.rotation.r.avoid", {"crop": current_name},
                                       PRIORITY_LOW))
    if not irrigated and climate["rain"] < 600 and chart_info is not None:
        recs.append(Recommendation("analysis.rotation.r.rainfed",
                                   {"mm": f"{climate['rain']:.0f}"}, PRIORITY_MEDIUM))
    recs.append(Recommendation("analysis.rotation.r.data", {}, PRIORITY_LOW))

    series = frames = None
    if chart_info is not None:
        dates, values = monthly(chart_info)
        grids = tuple(tuple(tuple(float(v) for _ in range(sources.GRID))
                            for _ in range(sources.GRID)) for v in values)
        series = Series("analysis.var.suitability_of", "%", tuple(dates), tuple(values),
                        {"crop": chart_name})
        frames = MapFrames("analysis.var.suitability_of", "%", tuple(dates), grids, 0.0, 100.0,
                           "suitability", {"crop": chart_name})
    return AnalysisResult("rotation", field.name, ROTATION_SOURCES, series, frames,
                          tuple(metrics), summary, summary_params, tuple(recs),
                          placeholder=False)


