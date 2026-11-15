"""Soil texture analysis: the field's clay / sand / silt on the USDA texture
triangle, with what the class means for water and management. Uses the
field's own data (SoilGrids or typed by the farmer); nothing is downloaded.
"""

from fieldshift.analysis.models import (
    LEVEL_GOOD, LEVEL_NEUTRAL, LEVEL_WARNING, PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_MEDIUM,
    AnalysisResult, DataSource, Metric, Recommendation, TextureFigure)
from fieldshift.fields.zone_data import usda_texture

SOURCES = (DataSource("SoilGrids 2.0", "analysis.var.soil_texture", "250 m · 0-30 cm"),
           DataSource("USDA", "analysis.var.texture_classes", ""))

# texture class -> family used for the advice
FAMILY = {"sand": "sandy", "loamy_sand": "sandy", "sandy_loam": "sandy",
          "loam": "loamy", "silt_loam": "silty", "silt": "silty",
          "sandy_clay_loam": "loamy", "clay_loam": "clayey", "silty_clay_loam": "clayey",
          "sandy_clay": "clayey", "silty_clay": "clayey", "clay": "clayey"}


def _value(field, key):
    data = field.data or {}
    return (data.get(key) or {}).get("value")


# (Field field)
# AnalysisResult with the triangle (figure), the fractions and the advice
def run_texture(field):
    clay, sand, silt = (_value(field, k) for k in ("clay", "sand", "silt"))
    texture = _value(field, "soil_texture")
    if clay is not None and sand is not None:
        silt = silt if silt is not None else max(0.0, 100 - clay - sand)
        texture = usda_texture(sand, silt, clay) or texture
    figure = TextureFigure(clay, sand, silt, texture)
    pct = lambda v: f"{v:.0f} %" if v is not None else "—"          # noqa: E731
    metrics = [Metric("analysis.texture.metric.class",
                      f"data_fields.soil_texture.{texture}" if texture else "—",
                      LEVEL_GOOD if FAMILY.get(texture) == "loamy" else LEVEL_NEUTRAL),
               Metric("analysis.texture.metric.clay", pct(clay)),
               Metric("analysis.texture.metric.sand", pct(sand)),
               Metric("analysis.texture.metric.silt", pct(silt))]
    water = _value(field, "available_water")
    if water is not None:
        metrics.append(Metric("analysis.texture.metric.water", f"{water:.1f} % vol",
                              LEVEL_WARNING if water < 10 else LEVEL_GOOD))
    family = FAMILY.get(texture)
    if family is None:
        summary, params = "analysis.texture.summary_unknown", {}
        recs = (Recommendation("analysis.texture.rec.unknown", {}, PRIORITY_HIGH),)
    else:
        summary = "analysis.texture.summary"
        params = {"texture": f"data_fields.soil_texture.{texture}", "clay": pct(clay),
                  "sand": pct(sand), "silt": pct(silt)}
        recs = tuple(Recommendation(f"analysis.texture.rec.{family}.{i}", {}, priority)
                     for i, priority in enumerate((PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)))
    return AnalysisResult("texture", field.name, SOURCES, None, None, tuple(metrics), summary,
                          params, recs, placeholder=False, figure=figure)
