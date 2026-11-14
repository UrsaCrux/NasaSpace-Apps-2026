"""Analyses of a field (vegetation, frost, water, heat, crop rotation).

No Qt and no QGIS here: an analysis takes a Field and returns an
AnalysisResult; fieldshift/ui/analysis_tab.py shows it. Every analysis is
listed ONCE in ANALYSES (registry.py). For now all of them are placeholders
that make up their numbers (placeholders.py); see docs/analysis.md.
"""

from fieldshift.analysis.models import (
    Analysis, AnalysisResult, DataSource, MapFrames, Metric, Recommendation, Series)
from fieldshift.analysis.registry import ANALYSES, get_analysis

__all__ = ["ANALYSES", "Analysis", "AnalysisResult", "DataSource", "MapFrames", "Metric",
           "Recommendation", "Series", "get_analysis"]
