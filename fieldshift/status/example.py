"""Example Status reports: made-up but plausible numbers, the same for the
same field and period. They stand in until the satellite sources
(NASA POWER, GPM IMERG, SMAP, MODIS, SoilGrids) are connected.
"""

import math
import random
import zlib
from datetime import date, timedelta

from fieldshift.analysis.models import TextureFigure
from fieldshift.fields.zone_data import usda_texture
from fieldshift.status.models import (
    CHART_BARS, LEVEL_ALERT, LEVEL_WATCH, StatusAlert, StatusReport, StatusRow,
    StatusSection, SummaryTile)


def _dates(days, today):
    return tuple((today - timedelta(days=days - i)).isoformat() for i in range(days))


def _wave(rng, days, base, swing, noise, low=None, high=None):
    phase = rng.uniform(0, math.tau)
    values = []
    for i in range(days):
        v = base + swing * math.sin(phase + i / 4.0) + rng.gauss(0, noise)
        if low is not None:
            v = max(low, v)
        if high is not None:
            v = min(high, v)
        values.append(v)
    return values


def _row(key, unit, dates, values, decimals=1, **options):
    return StatusRow(key, f"status.var.{key}", unit, dates,
                     tuple(round(v, decimals) for v in values), decimals=decimals, **options)


def _weather(rng, days, dates):
    tmax = _wave(rng, days, 24, 4, 1.5)
    tmin = [t - rng.uniform(9, 14) for t in tmax]
    rain = [0.0] * days
    for i in rng.sample(range(days), max(1, days // 5)):
        rain[i] = rng.uniform(1, 18)
    rain[-2] = rng.uniform(25, 40)                   # a heavy shower lately
    radiation = _wave(rng, days, 26, 3, 1.2, 8, 34)
    radiation[-1] = max(radiation[-1], 30.5)
    rows = (
        _row("temp_max", "°C", dates, tmax),
        _row("temp_min", "°C", dates, tmin),
        _row("rain", "mm", dates, rain, chart=CHART_BARS, source="GPM IMERG",
             level=LEVEL_WATCH),
        _row("humidity", "%", dates, _wave(rng, days, 55, 12, 4, 15, 100), 0),
        _row("radiation", "MJ/m²", dates, radiation, level=LEVEL_WATCH),
        _row("wind", "km/h", dates, _wave(rng, days, 12, 4, 2, 0), 0),
        _row("et0", "mm", dates, _wave(rng, days, 5, 1, 0.4, 0.5)),
    )
    rows = tuple(r if r.source else StatusRow(**{**r.__dict__, "source": "NASA POWER"})
                 for r in rows)
    alerts = (
        StatusAlert("status.alert.heavy_rain", {"mm": f"{rain[-2]:.0f}"}, LEVEL_WATCH,
                    suggestion=True),
        StatusAlert("status.alert.radiation", {"value": f"{radiation[-1]:.0f}"}, LEVEL_WATCH,
                    suggestion=True),
        StatusAlert("status.alert.rain_tomorrow", {"mm": f"{rng.uniform(15, 30):.0f}"},
                    LEVEL_ALERT, upcoming=True, suggestion=True),
        StatusAlert("status.alert.frost_upcoming", {"temp": f"{rng.uniform(-2, 1):.0f}",
                                                    "day": rng.randint(3, 6)},
                    LEVEL_WATCH, upcoming=True),
    )
    return StatusSection("weather", "status.section.weather", "🌤️", rows, alerts)


def _growth(rng, days, dates, crop):
    start = rng.uniform(0.45, 0.6)
    ndvi = [start + 0.004 * i + rng.gauss(0, 0.012) for i in range(days)]
    ndvi[-1] = ndvi[-1] - 0.06                    # a recent drop to warn about
    rows = (
        _row("ndvi", "", dates, ndvi, 2, source="MODIS", level=LEVEL_WATCH),
        _row("evi", "", dates, [v * 0.72 + rng.gauss(0, 0.01) for v in ndvi], 2,
             source="MODIS"),
        _row("lai", "m²/m²", dates, [v * 4.2 + rng.gauss(0, 0.05) for v in ndvi], 2,
             source="MODIS"),
        _row("height", "cm", dates, [18 + 0.6 * i for i in range(days)], 0,
             source="status.source.farmer"),
    )
    drop = (ndvi[-2] - ndvi[-1]) / ndvi[-2] * 100
    alerts = (StatusAlert("status.alert.ndvi_drop", {"pct": f"{drop:.0f}"}, LEVEL_WATCH,
                          suggestion=True),)
    day = rng.randint(30, 70)
    return StatusSection("growth", "status.section.growth", "🌱", rows, alerts,
                         note_key="status.stage", note_params={
                             "crop": crop or "—", "day": day,
                             "stage": f"status.stage.{'vegetative' if day < 50 else 'flowering'}"})


def _soil(rng, days, dates):
    moisture = _wave(rng, days, 24, 5, 1.2, 5, 50)
    moisture[-1] = min(moisture[-1], 17.5)
    rows = (
        _row("soil_moisture", "%", dates, moisture, source="SMAP", level=LEVEL_ALERT),
        _row("soil_temp", "°C", dates, _wave(rng, days, 17, 2.5, 0.6), source="NASA POWER"),
        _row("nitrogen", "g/kg", dates[-1:], (rng.uniform(0.8, 2.2),), 2, source="SoilGrids",
             fixed=True),
        _row("ph", "", dates[-1:], (rng.uniform(5.6, 7.6),), source="SoilGrids", fixed=True),
        _row("organic_carbon", "g/kg", dates[-1:], (rng.uniform(6, 22),), source="SoilGrids",
             fixed=True),
        _row("cec", "cmol/kg", dates[-1:], (rng.uniform(8, 25),), source="SoilGrids",
             fixed=True),
    )
    sand, clay = rng.uniform(25, 50), rng.uniform(12, 30)
    silt = 100 - sand - clay
    texture = TextureFigure(round(clay), round(sand), round(silt), usda_texture(sand, silt, clay))
    alerts = (
        StatusAlert("status.alert.dry_soil", {"value": f"{moisture[-1]:.0f}"}, LEVEL_ALERT,
                    suggestion=True),
        StatusAlert("status.alert.low_nitrogen", {"value": f"{rows[2].latest():.1f}"},
                    LEVEL_WATCH, suggestion=True) if rows[2].latest() < 1.5 else None,
    )
    return StatusSection("soil", "status.section.soil", "🟫", rows,
                         tuple(a for a in alerts if a), texture=texture)


# (Field field, int days = 7, date today = None, str crop = None)
# an example StatusReport of the field for the last days; crop is the crop
# name shown in the stage line
def example_report(field, days=7, today=None, crop=None):
    today = today or date.today()
    rng = random.Random(zlib.crc32(f"{field.name}|{days}".encode()))
    dates = _dates(days, today)
    weather = _weather(rng, days, dates)
    growth = _growth(rng, days, dates, crop)
    soil = _soil(rng, days, dates)
    pick = {r.key: r for s in (weather, growth, soil) for r in s.rows}
    summary = (
        SummaryTile("weather", pick["temp_max"], "🌡️"),
        SummaryTile("weather", pick["rain"], "🌧️"),
        SummaryTile("weather", pick["humidity"], "💧"),
        SummaryTile("weather", pick["radiation"], "☀️"),
        SummaryTile("growth", pick["ndvi"], "🌿"),
        SummaryTile("soil", pick["soil_moisture"], "🟫"),
    )
    return StatusReport(field.name, days, dates[-1], (weather, growth, soil), summary)


