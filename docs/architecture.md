# Architecture

```
┌──────────────────────────── MainWindow (QSplitter) ────────────────────────────┐
│                                                  │                             │
│   MapView.widget()                               │   SidePanel                 │
│   (QgsMapCanvas)                                 │   my fields · field data ·  │
│                                                  │   position · tools          │
│   FieldsBar: [Draw field]     [Export fields…]   │                             │
└──────────────────────────────────────────────────┴─────────────────────────────┘
          ▲  add_layer / set_center / ...                │
          │  cursor_moved / clicked / layers_changed     │
          └───────────────── MapView (abstract) ◄────────┘
                               ▲            ▲
                     QgisMapView   PlaceholderMapView
                         │
                    QGIS (qgis.core, qgis.gui)

   fieldshift.native ──ctypes──► cpp/build/libfieldshift_core.so
```

## Layers of the code

1. **UI** (`fieldshift/ui/`): Qt widgets. `MainWindow` puts the map widget on
   the left and the `SidePanel` on the right of a `QSplitter` (3:1 stretch,
   the user can drag the divider). Under the map sits the `FieldsBar`; a
   `ScaleBar` (`ui/scale_bar.py`) is drawn over its bottom-left corner.
   Over the map float the `MapControls` (top left; its magnifier opens the
   place search `MapSearch`, which uses Nominatim through
   `fieldshift/api/geocode.py`: 1 request per second, credit shown), the `WeatherCard` (top
   right: weather now and 7 days at the centre of the view, from Open-Meteo
   through `fieldshift/api/forecast.py`, credit shown on the card), the
   `HoverCard` and the `ScaleBar`. The window is a set of tabs: "Map" holds all of the above, and
   "Analyze…" adds one tab per analysis result (see
   [analysis.md](analysis.md)). Both
   share one `FieldsManager` (`fieldshift/fields/manager.py`), which saves
   the user's fields as GeoJSON and shows them as map layers, and remembers
   which fields the user checked in the panel list: the "Field data" box
   shows them (colour, area, date and zone data), "Export" and "Delete" act
   on them. A field's colour and zone data (`fieldshift/fields/schema.py`,
   one list `DATA_FIELDS`) are saved in its GeoJSON file. Base layers (`locked`)
   stay on the map but are not listed in the panel. The UI only
   knows `MapView`, `LayerSpec`, `LayerInfo` and `LayerKind`.
2. **Map abstraction** (`fieldshift/map/`): an engine-independent API. All
   coordinates are longitude/latitude in degrees. Notifications are plain
   Python `Event` objects, not Qt signals, so the abstraction does not
   depend on Qt and is easy to test or mock.
3. **Map backends**: `QgisMapView` wraps a `QgsMapCanvas` that draws in Web
   Mercator (EPSG:3857) and converts to and from EPSG:4326 at the boundary.
   `PlaceholderMapView` keeps layers in memory only, for machines without
   QGIS. `create_map_view()` picks one.
4. **Native core** (`cpp/` and `fieldshift/native/`): C++ compiled into a
   shared library with an `extern "C"` API, loaded with `ctypes`. Optional:
   the app runs without it.

## Start-up sequence (`fieldshift/app.py`)

1. Create a `QgsApplication` (or a `QApplication` without QGIS) and call
   `initQgis()`.
2. `create_map_view()`.
3. Add the default layers, bottom first: `data/countries.geojson` (works
   offline), then the Sentinel-2 cloudless satellite tiles (EOX), whose credit
   is shown in the status bar.
4. Centre on Santiago, build `MainWindow`, run the event loop.

## Rules that keep it editable

- UI code never imports `qgis.*`. If a feature needs something the
  abstraction does not offer, add a method to `MapView` and implement it in
  every backend (see [map-abstraction.md](map-abstraction.md)).
- QGIS-only power features can use `QgisMapView.canvas()`, but keep that code
  in `fieldshift/map/`.
- Import Qt from `fieldshift.qt`, never from `PyQt6` directly: QGIS ships its
  own PyQt build.
- Qt6 rules: write enums fully scoped (`Qt.Orientation.Horizontal`,
  `Qt.ItemDataRole.UserRole`, `Qt.CheckState.Checked`) and call `exec()`,
  not `exec_()`.
- Only C types cross the Python/C++ boundary.
