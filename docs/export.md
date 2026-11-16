# Export

Two ways, both write one **ZIP**:

1. **Export this analysis…** (header of every analysis tab): the analysis on
   screen — `informe.pdf` (summary, metrics, chart, map, recommendations,
   sources), `<field>/analisis/<id>.json` (the whole result), `<id>.csv` (the
   series) and the PNG pictures.
2. **Export…** in the bar under the map (`ui/export_dialog.py`): choose the
   fields and what to include, or a preset:
   - **Only GeoJSON** — field shape, data and measurements (instant);
   - **Status + Trends** — adds today + forecast and the last 12 months;
   - **Everything** — adds every analysis (minutes: each one downloads data).
   A progress window downloads in a worker thread (cancellable) and then writes:

```
PACHI_export_<date>.zip
  informe.pdf                  readable report of everything chosen, per field
  manifest.json                app version, date, list of files
  <field>/terreno.geojson      the field (data and measurements included)
  <field>/mediciones.csv       measurements
  <field>/status.json, pronostico.csv, pronostico_*.png
  <field>/trends.json, trends.csv, trends_*.png
  <field>/analisis/<id>.json, <id>.csv, <id>_grafico.png, <id>_mapa.png
```

A part that could not be downloaded is written in the report with its reason
(no connection, timeout…), never with made-up numbers.

Code: `fieldshift/export/collect.py` (what to export, downloading; no Qt) and
`fieldshift/export/write.py` (charts drawn with the app's widgets, PDF with
`QTextDocument` + `QPdfWriter`, ZIP).
