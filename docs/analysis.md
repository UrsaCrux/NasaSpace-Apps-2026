# Analyses

"Analyze…" (bar under the map) opens a dialog: choose **one field** and one
or more **analyses**. A progress window runs them, then each result opens in
its own tab next to the "Map" tab. Tabs can be closed; the map tab cannot.

Every analysis uses **real data** (the old made-up versions stay in
`fieldshift/analysis/placeholders.py`, only for UI tests). Time series cover
the last 24 complete months; the map part shows real pixels or the field's
relief. When a source cannot be reached the tab says the data is not
available — no made-up numbers.

| Analysis | Data | Map |
|----------|------|-----|
| **Vegetation productivity** (`real.py`) | FAO WaPOR v3 net primary production, monthly | WaPOR 300 m pixels over the field |
| **Frost** (`real.py`) | NASA POWER daily minimum (coldest of each month, frost days), Open-Meteo 7-day forecast, POWER typical frost days | temperature spread over the Copernicus DEM relief (−6.5 °C/km) |
| **Water balance** (`real.py`) | NASA POWER rain − WaPOR actual evapotranspiration, monthly | balance per WaPOR pixel |
| **Heat** (`real.py`) | NASA POWER daily maximum; days above the crop's optimal maximum (FAO EcoCrop) or 32 °C | temperature over the relief |
| **Rotation** (`real.py`) | catalogue field crops scored against POWER climate normals, the field's pH and texture and irrigation, with their EcoCrop requirements; compares the **current crop**, a **diversified** rotation (cereal → legume → break crop) and a **soil-building** one, with a sowing month | temperature suitability of the season-1 crop, next 12 months |
| **Soil texture** (`texture.py`) | the field's clay / sand / silt on the USDA triangle | (the triangle) |
| **Crop growth** (`crop_growth.py`) | WOFOST / PCSE simulation — see [simulation.md](simulation.md) | leaf area index |

Data access is in `fieldshift/analysis/sources.py` (cached per session);
`tests/fake_sources.py` replaces it with synthetic data in the tests.

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
