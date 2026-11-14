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
| `data` | Zone data and crop: `{key: {"value": ..., "source": "prefilled" \| "user" \| "missing"[, "prefilled": <loaded value>]}}`; the crop is `data.crop = {"value": "<variety id>", "source": "user"}` |

Files without `color` or `data` (older versions) open with grey, no crop and
every datum `missing` (the dialog then loads them). Data keys of older
versions (`soil_type`, `annual_rain_mm`) are dropped. "Export" writes the same
properties.

## Editing a field

Each row of "My fields" has an **Edit** button. It opens the same dialog as
"Draw field", with the current name, colour and data. Saving rewrites the
file (renamed if the name changed; the field's own name is not a duplicate),
redraws the map layer and updates the list and the data box. The checkbox of
the field stays as it was. The code is `FieldStore.update` and
`FieldsManager.update`; the button is drawn by `ui/field_list.py`.

## The "Save as field" dialog

Opened after drawing a field (and by **Edit**). It asks for:

- **Name** — required, unique.
- **Crop** — required. A search box: typing "peach", "durazno" or
  "melocotón" (any language, accents and case ignored) opens a dropdown with
  the matching varieties ("Peach – variety 1", "Durazno – variedad 1"...).
  Only a variety picked from the list (or typed exactly) counts. The list is
  `fieldshift/crops/crops.json` — **placeholder varieties** for now (46 real
  crop names, 3 made-up varieties each); search code in
  `fieldshift/crops/__init__.py`.
- **Colour** — optional.
- **Zone data** — loaded from the data sources (below), editable.

Save stays disabled until the name and crop are valid **and** every data
source has answered or run out of time.

## Zone data: one list

The data of the zone are described by `DATA_FIELDS` in
`fieldshift/fields/schema.py`, grouped in the dialog:

| Group | Data | Source (`fieldshift/fields/zone_data.py`) |
|-------|------|-------------------------------------------|
| Soil (top 30 cm) | texture (USDA class from clay/sand/silt), soil group (WRB), pH, organic carbon, nitrogen, CEC, available water (field capacity − wilting point) | SoilGrids, depth-weighted 0–30 cm |
| Relief | elevation, slope | Copernicus DEM GLO-30 |
| Vegetation | NDVI | MODIS MOD13Q1 (ORNL) |
| Vegetation | biomass production (NPP), actual evapotranspiration | FAO WaPOR v3 |
| Farm | irrigated | typed by the farmer |

No weather here on purpose: that belongs to the analyses.

**Loading.** The field is turned into a circle (polygon centroid, radius with
the same area) and each source runs in its own thread (`ZoneDataLoader` in
`ui/field_dialog.py`), so the fast ones (DEM ~5 s, WaPOR ~6 s, SoilGrids
~10 s) fill their rows without waiting for the slow one (MODIS ~30 s). While
a row loads it shows a small animation and cannot be edited. Each source
has its own time budget (`timeout_s`, 20–40 s); a source that fails or runs
out of time leaves its rows **orange, "not available"** (the reason is in the
tooltip), and they can be typed in. Results are cached per place for the
session. When editing a field, only sources with an empty row are asked
again, and rows with a value keep it. `FIELDSHIFT_OFFLINE=1` never contacts
the sources (the tests set it).

**States of a datum.** `prefilled` (from a source, grey) · `user` (edited,
green bold; a ↺ button restores the loaded value, kept in `"prefilled"`) ·
`missing` (no value, orange).

**Changing the data.**

1. Edit `DATA_FIELDS` (key, kind `choice` / `number` / `bool`, range, unit,
   group).
2. Add the texts to `en.json` and `es.json`: `data_fields.<key>` and, for a
   choice, `data_fields.<key>.<option>`.
3. If a data source fills it, add the key to a `SourceGroup` in
   `zone_data.py` (or a new group: provider, keys, how to read them from the
   `SiteData`, timeout).

The dialog, the data box and the files follow the list; nothing else changes.
