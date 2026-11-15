# Analyses

"Analyze…" (bar under the map) opens a dialog: choose **one field** and one
or more **analyses**. A progress window runs them, then each result opens in
its own tab next to the "Map" tab. Tabs can be closed; the map tab cannot.

Most analyses are **placeholders** for now: their numbers are made up
(`fieldshift/analysis/placeholders.py`) and their tabs show an "Example
data" badge. Two use real data:

| Analysis | What it shows |
|----------|---------------|
| **Soil texture** (`texture.py`) | the USDA texture triangle (12 classes, coloured, names in the current language) with the field's clay / sand / silt point and its class outlined; the fractions, class, available water and advice for that kind of soil. No time line: the tab shows the triangle instead of the chart and map |
| **Crop growth** (`crop_growth.py`) | a WOFOST / PCSE simulation of the crop's season — see [simulation.md](simulation.md) |

Analyses run in a worker thread while the progress window is shown, so long
ones (downloads, the simulation) do not freeze the window.

## A result tab

```
+---------------------------+---------------------------+
| Data: sources, chart and  | Map: the field coloured   |
| a time slider (play)      | for the selected date     |
+---------------------------+---------------------------+
| Results: summary and      | Recommendations, most     |
| key numbers               | urgent first              |
+---------------------------+---------------------------+
```

The slider (or ▶) moves the chart cursor and the map together. The map part
is a simple preview (`FieldPreview`); when real rasters exist it becomes a
`MapView`.

## Code

| Where | What |
|-------|------|
| `fieldshift/analysis/models.py` | `Analysis`, `AnalysisResult`, `Series`, `MapFrames`, `Metric`, `Recommendation`, `DataSource`, `TextureFigure` (no Qt). `series` / `frames` may be `None` for results without a time line; `figure` is then drawn instead |
| `fieldshift/analysis/registry.py` | **the one list** `ANALYSES` |
| `fieldshift/analysis/placeholders.py` | made-up `run_*` functions (PLACEHOLDER) |
| `fieldshift/ui/analyze_dialog.py` | field + analyses dialog, progress window |
| `fieldshift/ui/analysis_tab.py` | the four-part tab |
| `fieldshift/ui/analysis_widgets.py` | line chart, field preview, colour scales, texture triangle |

Texts are i18n keys (`analysis.<id>.*`); values may contain keys such as
`month.7` or `crop.wheat`, which the UI translates.

## Adding or replacing an analysis

1. Write `run(field) -> AnalysisResult`. For real data use
   `fieldshift.api.get_site_data` (ERA5-Land, GPM IMERG, WaPOR, SMAP,
   SoilGrids...) and set `placeholder=False`.
2. Add (or replace) its `Analysis` entry in `ANALYSES`.
3. Add its texts to `en.json` and `es.json`. `tests/test_analysis.py` checks
   that every text a result uses exists in both files.
