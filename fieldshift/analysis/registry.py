"""The ONE list of analyses the user can choose. All use real data
(fieldshift/analysis/real.py, texture.py, crop_growth.py); placeholders.py
keeps the old made-up versions for UI tests.

To add an analysis: write its run(field) function (returning an
AnalysisResult), add an Analysis entry here and its texts to the i18n files
(``analysis.<id>.*``). The dialog, the progress window and the result tabs
follow this list.
"""

from fieldshift.analysis import real
from fieldshift.analysis.crop_growth import SOURCES_BASE as CROP_GROWTH_SOURCES
from fieldshift.analysis.crop_growth import run_crop_growth
from fieldshift.analysis.models import Analysis
from fieldshift.analysis.texture import SOURCES as TEXTURE_SOURCES
from fieldshift.analysis.texture import run_texture

# in the order the dialog shows them; rotation comes last because it uses
# what the others find
ANALYSES = (
    Analysis("vegetation", "analysis.vegetation.title", "analysis.vegetation.short",
             "analysis.vegetation.description", real.VEGETATION_SOURCES, real.run_vegetation),
    Analysis("frost", "analysis.frost.title", "analysis.frost.short",
             "analysis.frost.description", real.FROST_SOURCES, real.run_frost),
    Analysis("water", "analysis.water.title", "analysis.water.short",
             "analysis.water.description", real.WATER_SOURCES, real.run_water),
    Analysis("heat", "analysis.heat.title", "analysis.heat.short",
             "analysis.heat.description", real.HEAT_SOURCES, real.run_heat),
    Analysis("texture", "analysis.texture.title", "analysis.texture.short",
             "analysis.texture.description", TEXTURE_SOURCES, run_texture),
    Analysis("crop_growth", "analysis.crop_growth.title", "analysis.crop_growth.short",
             "analysis.crop_growth.description", CROP_GROWTH_SOURCES, run_crop_growth),
    Analysis("rotation", "analysis.rotation.title", "analysis.rotation.short",
             "analysis.rotation.description", real.ROTATION_SOURCES, real.run_rotation),
)


# (str analysis_id)
# the Analysis with this id; raises KeyError when there is none
def get_analysis(analysis_id):
    for analysis in ANALYSES:
        if analysis.id == analysis_id:
            return analysis
    raise KeyError(analysis_id)
