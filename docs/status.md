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

Series are cached in memory. **No made-up numbers are ever shown**: when a
source fails the panel says why (`api/errors.py`: no internet connection,
timeout, the service failed — HTTP code —, no data, offline) with a **Try
again** button; when only some sources fail (Trends: normals, MODIS) the rest
shows with a red box naming the missing ones. The example generators
(`status/example.py`, `trends/example.py`) are only used by the tests
(`FIELDSHIFT_OFFLINE=1` + `FIELDSHIFT_EXAMPLE_DATA=1`).

## Measurements (records)

Farmers and agronomists can record measurements and events with **date and
time** (`fields/records.py`): soil probe moisture, soil temperature, pH, EC,
nitrogen, organic carbon, CEC, plant height, pods, sowing, fertiliser,
irrigation, harvest. They are kept in the field's GeoJSON file (property
`records`), so they travel with it (a SQLite database could replace this when
there are many; not needed yet).

- Added from **Measurements…** (right-click menu of a field) or "Add or see
  measurements →" in Status (`ui/records_dialog.py`).
- Values typed in **Edit field** become records too ("edited"), and the newest
  pH / nitrogen / organic carbon / CEC record becomes the field's datum, so both
  places agree and Analyze uses the measured value.
- **Status**: a soil moisture / temperature measured today replaces the
  forecast's tile ("measured at 10:20"); the follow-up shows days since sowing
  and the plant height (and its change).
- **Trends**: a "Your measurements" section, month by month.
- Without records, the satellite / model values are used.

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
