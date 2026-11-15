# Status

How one field is **now**: the last 7 / 14 / 30 days of observed data, plus
short warnings about the next days. Longer periods are in **Trends**; plans
and suggestions are in **Analyze**.

| Area | Looks at | Example |
|---|---|---|
| Status | the present: last ≤ 30 days + warnings for the next 7 | "48 mm of rain yesterday, young plants: check erosion" |
| Trends | the past: season, year, earlier years | NDVI curve of the season vs last year |
| Analyze | the future and decisions | crop rotation, fertiliser plan, harvest estimate |

## Pieces

- `fieldshift/status/models.py` — plain data: `StatusReport` → `StatusSection`
  (weather, growth, soil) → `StatusRow` (one variable, one value per day) and
  `StatusAlert` (`upcoming` = about the next days, `suggestion` = links to Analyze).
- `fieldshift/status/example.py` — made-up numbers, the same for the same field
  and period (`report.example` is True; the panel shows a banner).
- `fieldshift.status.status_report(field, days)` — the entry point. To connect
  real data, build the same `StatusReport` from NASA POWER, GPM IMERG, SMAP,
  MODIS and SoilGrids and set `example=False`.
- `fieldshift/ui/status_panel.py` — the right column of the map tab while
  **Status** is chosen in the bar (it swaps with **My fields**; field chooser
  and period on top, scrolling content). Clicking another field on the map
  shows it; choosing one in the list also moves the map to it.
- `fieldshift/ui/status_widgets.py` — summary tiles (click → jumps to the row),
  section table (click a row → chart), chart with hover read-out, alert rows,
  USDA texture triangle (reused from `analysis_widgets.TextureTriangle`).

The bar under the map switches the right column: **My fields** | **Status**.
**Draw field** floats over the bottom-right corner of the map. Status opens from
the bar or from the right-click
menu of a field (`MainWindow.open_status(layer_id)`).
