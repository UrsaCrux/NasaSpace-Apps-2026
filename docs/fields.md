# Fields (terrenos)

A *field* is a plot the user draws on the map. Code: `fieldshift/fields/`
(no Qt, no QGIS) and `fieldshift/ui/` (`fields_bar.py`, `field_dialog.py`,
`fields_data.py`, `side_panel.py`).

## Where they are saved

`terrenos/` in the repository root (ignored by git), one GeoJSON file per
field, named after the field. `FIELDSHIFT_FIELDS_DIR` changes the folder.
Files from the old folder `data/local/fields/` are moved to `terrenos/` the
first time the app starts.

Each file is a FeatureCollection with one Feature (EPSG:4326). Properties:

| Property | Meaning |
|----------|---------|
| `name` | Name shown in the app (required, unique ignoring case) |
| `area_ha` | Area in hectares |
| `created` | Creation date (ISO 8601, UTC) |
| `color` | `"#rrggbb"`; grey `#9e9e9e` if never chosen |
| `data` | Zone data: `{key: {"value": ..., "source": "prefilled" \| "user"}}` |

Files without `color` or `data` (older versions) open with grey and with
prefilled data. "Export" writes the same properties.

## Zone data: one list

The data of the zone (soil type, pH, annual rainfall, irrigation) are
described by `DATA_FIELDS` in `fieldshift/fields/schema.py`. **Those four are
placeholders**, and so are their values: `_lookup_zone_value` makes up values
from the coordinates. To change the data:

1. Edit `DATA_FIELDS` (key, kind `choice` / `number` / `bool`, range, unit).
2. Add the texts to `en.json` and `es.json`: `data_fields.<key>` and, for a
   choice, `data_fields.<key>.<option>`.
3. To use real data, replace the body of `_lookup_zone_value` (SoilGrids,
   NASA POWER...) and delete the placeholder section.

The dialog, the data box and the files follow the list; nothing else changes.
Each datum is `prefilled` until the user edits it (then `user`); a button in
the dialog brings the prefilled value back.
