# Status and Trends

Two views of one field in the right column of the map tab, chosen in the bar
under the map: **My fields** | **Status** | **Trends**. Clicking another field on
the map shows it; choosing one in the panel's list also moves the map to it.

| Area | Looks at | Example |
|---|---|---|
| Status | the present: "today" tiles, each against the mean of the last 7 / 14 / 30 days | max temperature 24 °C, ↑ 2.1 vs 7-day mean |
| Trends | the past: the last 12 months vs the year before and the normal | wettest month, seasons, NDVI curve |
| Analyze | the future and decisions | crop rotation, fertiliser plan |

Status shows only the "today" tiles for now (the per-section tables, charts and
warnings were taken out as not stable yet); the report (`StatusReport`) still
carries sections, warnings and the 7-day forecast for later views.

## Data sources

| What | Source | Notes |
|---|---|---|
| Temperature, rain, humidity, sun, wind | NASA POWER daily (`status/sources.py`) | ~0.5°, ~3 days late, no key |
| Evapotranspiration | computed (Hargreaves) from POWER temperature + sun | |
| Top-soil wetness, surface temperature | NASA POWER `GWETTOP`, `TS` | % of saturation |
| NDVI | MODIS MOD13Q1 via ORNL DAAC | 16-day composites, ~1 month late, slow |
| Nitrogen, pH, organic carbon, CEC, texture | the field's stored data (SoilGrids or typed) | fixed values |
| Next 7 days | Open-Meteo forecast | kept in the report |
| Normals (Trends) | NASA POWER climatology | rain, humidity, sun |

Every series is cached in memory per place and day. A source that fails only
leaves its rows out (listed as "no answer from" in the info line); when NASA
POWER fails, or with `FIELDSHIFT_OFFLINE=1` (tests), the panels show example
data and the info line says so.

## Code

- `fieldshift/status/` — `models.py` (StatusReport → sections → rows / alerts),
  `sources.py` (POWER daily + climatology, MODIS NDVI, ET0), `rules.py` (warning
  thresholds), `live.py` (real report), `example.py` (made-up report),
  `status_report(field, days)` entry point.
- `fieldshift/trends/` — `models.py` (TrendsReport: rows with this year / year
  before / normal, milestones, seasons), `build.py` (monthly series → report),
  `live.py`, `example.py`, `trends_report(field)` entry point.
- `fieldshift/ui/field_panel.py` — base of both panels: field chooser, map clicks,
  loading in a background thread, info line.
- `fieldshift/ui/status_panel.py`, `status_widgets.py` — Status view (tiles).
- `fieldshift/ui/trends_panel.py`, `trends_widgets.py` — Trends view (milestones,
  seasons table, 12-month charts with hover, crop card).

`MainWindow.open_status(layer_id)` / `open_trends(layer_id)` open them (also from
the right-click menu of a field).
