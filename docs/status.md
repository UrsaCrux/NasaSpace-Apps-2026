# Status and Trends

Two views of one field in the right column of the map tab, chosen in the bar
under the map: **My fields** | **Status** | **Trends**. Clicking another field on
the map shows it; choosing one in the panel's list also moves the map to it.

| Area | Looks at | Example |
|---|---|---|
| Status | today and the coming 7 / 14 days, light warnings, crop follow-up | "Tomorrow: about 18 mm of rain" |
| Trends | the past: the last 12 months vs the year before and the normal | wettest month, seasons, NDVI curve |
| Analyze | decisions and suggestions | crop rotation, fertiliser plan |

The weather card over the map shows today hour by hour; the coming days are
in Status.

## Status

1. **Today** — tiles from the Open-Meteo forecast: temperature now (max/min),
   rain today (chance), humidity, wind, sun (UV), crop water use (ET0), top-soil
   water and temperature this hour.
2. **Coming days** — 7 or 14 days (the service gives up to 16): a chart per
   variable (temperature, rain, wind, humidity, sun), a day slider with ▶ play,
   the chosen day's details and light warnings (`status/rules.py`: big
   temperature change, rain, frost, heat, wind, strong sun). "More in Analyze →"
   opens Analyze.
3. **Crop follow-up** — crop name, newest MODIS NDVI and its change against the
   image before (loaded apart: MODIS takes tens of seconds).

## Data sources

| What | Source | Notes |
|---|---|---|
| Today, hours, next 16 days | Open-Meteo forecast (`api/forecast.py`) | no key, CC BY 4.0 |
| Crop follow-up (NDVI) | MODIS MOD13Q1 via ORNL DAAC | 16-day images, ~1 month late, slow |
| Trends: weather, top-soil wetness | NASA POWER daily (`status/sources.py`) | ~0.5°, ~3 days late |
| Trends: normals | NASA POWER climatology | rain, humidity, sun |
| Trends: NDVI | MODIS | monthly means of the images |

Series are cached in memory. Offline (`FIELDSHIFT_OFFLINE=1`, tests) or when the
forecast / NASA POWER fails, the panels show example data and the info line
says so.

## Code

- `fieldshift/status/` — `models.py` (StatusReport: today tiles, forecast,
  warnings; Tracking), `build.py` (today tiles), `rules.py` (light warnings),
  `sources.py` (POWER daily + climatology, MODIS NDVI, ET0; used by Trends and
  the follow-up), `live.py`, `example.py`; entry points `status_report(field)`
  and `crop_tracking(field)`.
- `fieldshift/trends/` — `models.py` (TrendsReport: rows with this year / year
  before / normal, milestones, seasons), `build.py` (monthly series → report),
  `live.py`, `example.py`, `trends_report(field)` entry point.
- `fieldshift/ui/field_panel.py` — base of both panels: field chooser, map clicks,
  loading in a background thread, info line.
- `fieldshift/ui/status_panel.py`, `status_widgets.py` — Status view (today
  tiles, ForecastCard, TrackingCard).
- `fieldshift/ui/trends_panel.py`, `trends_widgets.py` — Trends view (milestones,
  seasons table, 12-month charts with hover, crop card).

`MainWindow.open_status(layer_id)` / `open_trends(layer_id)` open them (also from
the right-click menu of a field).
