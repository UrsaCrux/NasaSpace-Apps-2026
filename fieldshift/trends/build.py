"""Turns monthly series into a TrendsReport: rows, milestones and seasons.
Shared by the real report (live.py) and the example one (example.py).
"""

from fieldshift.trends.models import (
    AGG_MEAN, AGG_SUM, CHART_BARS, Milestone, SeasonRow, TrendRow, TrendSection, TrendsReport)

# season of each month (1..12) in the southern hemisphere; northern is shifted
_SOUTH = {12: "summer", 1: "summer", 2: "summer", 3: "autumn", 4: "autumn", 5: "autumn",
          6: "winter", 7: "winter", 8: "winter", 9: "spring", 10: "spring", 11: "spring"}
_FLIP = {"summer": "winter", "winter": "summer", "autumn": "spring", "spring": "autumn"}
# rows: key, unit, aggregate, chart, decimals, section
ROWS = (
    ("temp_max", "°C", AGG_MEAN, None, 1, "weather"),
    ("temp_min", "°C", AGG_MEAN, None, 1, "weather"),
    ("rain", "mm", AGG_SUM, CHART_BARS, 0, "weather"),
    ("humidity", "%", AGG_MEAN, None, 0, "weather"),
    ("radiation", "MJ/m²", AGG_MEAN, None, 1, "weather"),
    ("et0", "mm", AGG_SUM, CHART_BARS, 0, "weather"),
    ("ndvi", "", AGG_MEAN, None, 2, "growth"),
    ("soil_moisture", "%", AGG_MEAN, None, 0, "soil"),
    ("soil_temp", "°C", AGG_MEAN, None, 1, "soil"),
    ("water_balance", "mm", AGG_SUM, CHART_BARS, 0, "soil"),
)
SECTIONS = (("weather", "status.section.weather", "🌤️"),
            ("growth", "status.section.growth", "🌱"),
            ("soil", "trends.section.soil", "🟫"))


# record kinds whose months add up (the rest are means)
SUM_KINDS = ("fertilizer", "irrigation", "harvest")


# (tuple records, tuple months)
# the farmer's records with a value, month by month: {kind: [value or None
# per month]} (sums for SUM_KINDS, means for the rest); kinds without any
# record in the months are left out
def measured_series(records, months):
    from fieldshift.fields.records import KINDS
    out = {}
    for kind, (_, _, _, has_value) in KINDS.items():
        if not has_value:
            continue
        values = []
        for month in months:
            found = [r.value for r in records
                     if r.kind == kind and r.value is not None and r.time.startswith(month)]
            if not found:
                values.append(None)
            else:
                values.append(sum(found) if kind in SUM_KINDS else sum(found) / len(found))
        if any(v is not None for v in values):
            out[kind] = values
    return out


# (str month, float lat)
# season key of "YYYY-MM" at that latitude
def season_of(month, lat):
    name = _SOUTH[int(month[5:7])]
    return name if lat < 0 else _FLIP[name]


def _pick(values, months, best):
    known = [(v, m) for v, m in zip(values, months) if v is not None]
    return best(known, key=lambda p: p[0]) if known else None


# (str field_name, tuple months, float lat, dict series, dict previous,
#  dict normal, dict sources, dict counts, str crop, bool example, tuple missing)
# series / previous / normal: {row key: [value or None per month]}; sources:
# {row key: source name}; counts: {"frost_days": n, "heavy_rain_days": n}
def make_report(field_name, months, lat, series, previous, normal, sources, counts,
                crop=None, example=False, missing=(), measured=None):
    rows = {}
    for key, unit, aggregate, chart, decimals, _ in ROWS:
        values = series.get(key)
        if not values or all(v is None for v in values):
            continue

        def rounded(xs):
            return tuple(None if v is None else round(v, decimals) for v in xs) if xs else None
        rows[key] = TrendRow(key, f"status.var.{key}", unit, months, rounded(values),
                             rounded(previous.get(key)), rounded(normal.get(key)), aggregate,
                             chart or "line", decimals, sources.get(key, ""))
    sections = tuple(TrendSection(sid, title, icon, tuple(
        rows[k] for k, *_rest, section in ROWS if section == sid and k in rows))
        for sid, title, icon in SECTIONS)
    if measured:
        # the farmer's own measurements, apart from the satellite rows
        from fieldshift.fields.records import KINDS
        own = []
        for kind, values in measured.items():
            unit, decimals = KINDS[kind][0], KINDS[kind][1]
            own.append(TrendRow(kind, f"records.kind.{kind}", unit, months,
                                tuple(None if v is None else round(v, decimals) for v in values),
                                aggregate=AGG_SUM if kind in SUM_KINDS else AGG_MEAN,
                                chart=CHART_BARS if kind in SUM_KINDS else "line",
                                decimals=decimals, source="status.source.farmer"))
        sections += (TrendSection("measured", "trends.section.measured", "", tuple(own)),)

    milestones = []

    def add(icon, label, key, best, fmt):
        if key not in rows:
            return
        found = _pick(rows[key].values, months, best)
        if found:
            milestones.append(Milestone(icon, label, fmt(found[0]), found[1]))
    add("🌧️", "trends.milestone.wettest", "rain", max, lambda v: f"{v:.0f} mm")
    add("🏜️", "trends.milestone.driest", "rain", min, lambda v: f"{v:.0f} mm")
    add("🔥", "trends.milestone.hottest", "temp_max", max, lambda v: f"{v:.1f} °C")
    add("❄️", "trends.milestone.coldest", "temp_min", min, lambda v: f"{v:.1f} °C")
    add("🌿", "trends.milestone.greenest", "ndvi", max, lambda v: f"NDVI {v:.2f}")
    add("🍂", "trends.milestone.least_green", "ndvi", min, lambda v: f"NDVI {v:.2f}")
    add("💧", "trends.milestone.wettest_soil", "soil_moisture", max, lambda v: f"{v:.0f}%")
    add("⚖️", "trends.milestone.deficit", "water_balance", min, lambda v: f"{v:.0f} mm")
    if "frost_days" in counts:
        milestones.append(Milestone("🧊", "trends.milestone.frost_days",
                                    str(counts["frost_days"])))
    if "heavy_rain_days" in counts:
        milestones.append(Milestone("⛈️", "trends.milestone.heavy_rain_days",
                                    str(counts["heavy_rain_days"])))
    rain = rows.get("rain")
    if rain and rain.normal_total():
        pct = (rain.total() / rain.normal_total() - 1) * 100
        milestones.append(Milestone("📊", "trends.milestone.rain_vs_normal",
                                    f"{pct:+.0f}%"))

    # seasons as runs of consecutive months; a lone first month is left out
    runs = []
    for i, month in enumerate(months):
        name = season_of(month, lat)
        if runs and runs[-1][0] == name:
            runs[-1][1].append(i)
        else:
            runs.append((name, [i]))
    if len(runs) > 1 and len(runs[0][1]) == 1:
        runs = runs[1:]
    seasons = []
    for name, idx in runs:

        def agg(key, how):
            vals = [series[key][i] for i in idx if key in series and series[key][i] is not None]
            if not vals:
                return None
            return sum(vals) if how == AGG_SUM else sum(vals) / len(vals)
        temps = [agg("temp_max", AGG_MEAN), agg("temp_min", AGG_MEAN)]
        seasons.append(SeasonRow(f"trends.season.{name}", months[idx[0]][:4],
                                 tuple(months[i] for i in idx), {
            "temp": None if None in temps else sum(temps) / 2,
            "rain": agg("rain", AGG_SUM), "water_balance": agg("water_balance", AGG_SUM),
            "ndvi": agg("ndvi", AGG_MEAN), "soil_moisture": agg("soil_moisture", AGG_MEAN)}))
    return TrendsReport(field_name, tuple(months), sections, tuple(milestones), tuple(seasons),
                        crop, example, missing=tuple(missing))
