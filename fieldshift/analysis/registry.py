"""The ONE list of analyses the user can choose.

To add an analysis: write its run(field) function (returning an
AnalysisResult), add an Analysis entry here and its texts to the i18n files
(``analysis.<id>.*``). The dialog, the progress window and the result tabs
follow this list.
"""

from fieldshift.analysis import placeholders as ph
from fieldshift.analysis.models import Analysis

# in the order the dialog shows them; rotation comes last because it uses
# what the others find
ANALYSES = (
    Analysis("vegetation", "analysis.vegetation.title", "analysis.vegetation.short",
             "analysis.vegetation.description", ph.VEGETATION_SOURCES, ph.run_vegetation),
    Analysis("frost", "analysis.frost.title", "analysis.frost.short",
             "analysis.frost.description", ph.FROST_SOURCES, ph.run_frost),
    Analysis("water", "analysis.water.title", "analysis.water.short",
             "analysis.water.description", ph.WATER_SOURCES, ph.run_water),
    Analysis("heat", "analysis.heat.title", "analysis.heat.short",
             "analysis.heat.description", ph.HEAT_SOURCES, ph.run_heat),
    Analysis("rotation", "analysis.rotation.title", "analysis.rotation.short",
             "analysis.rotation.description", ph.ROTATION_SOURCES, ph.run_rotation),
)


# (str analysis_id)
# the Analysis with this id; raises KeyError when there is none
def get_analysis(analysis_id):
    for analysis in ANALYSES:
        if analysis.id == analysis_id:
            return analysis
    raise KeyError(analysis_id)
