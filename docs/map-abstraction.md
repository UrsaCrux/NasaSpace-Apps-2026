# Map abstraction layer

Package: `fieldshift.map`. Everything outside this package uses the map only
through these names:

```python
from fieldshift.map import MapView, LayerSpec, LayerInfo, LayerKind, Event, create_map_view
```

The full generated reference is in [api/PYTHON_API.md](api/PYTHON_API.md).

## Describing layers: `LayerSpec`

```python
LayerSpec.xyz("Basemap", "https://tiles.example.org/{z}/{y}/{x}.jpg", attribution="Imagery by Example")
LayerSpec.vector("Fields", "/path/fields.gpkg", fill_color="#cfe8b0", stroke_color="#4a7a2a")
LayerSpec.raster("NDVI", "/path/ndvi.tif")
```

| Field | Meaning |
|-------|---------|
| `name` | Display name |
| `source` | URL template (XYZ), or any path / URI OGR or GDAL can open |
| `kind` | `LayerKind.XYZ`, `VECTOR` or `RASTER` |
| `options` | Backend hints: `zmin`/`zmax` (XYZ), `provider` (force a data provider, e.g. `"memory"`), `locked` (base layer such as the basemap: the side panel does not list it, so the user cannot remove it; reported as `LayerInfo.locked`), `attribution` (credit text the window shows in the status bar while the layer is visible; reported as `LayerInfo.attribution`), `fill_color`/`stroke_color` (vectors; `"#AARRGGBB"` for transparency), `stroke_width` (vectors, mm), `label_field` (vectors: attribute shown over each feature, with a halo; also `label_color`, `label_halo_color`, `label_size`) |

## Using the map: `MapView`

| Method | Description |
|--------|-------------|
| `widget()` | The `QWidget` to embed |
| `add_layer(spec) -> id` | Load on top; raises `ValueError` if the source cannot be opened |
| `remove_layer(id)` | Remove |
| `layers() -> [LayerInfo]` | Loaded layers, top first |
| `set_layer_visible(id, bool)` | Show / hide |
| `set_center(lon, lat, scale=None)` | Centre, optionally at a scale such as `5_000_000` (1:5M) |
| `zoom_to_extent(xmin, ymin, xmax, ymax)` | Fit a lon/lat box |
| `zoom_to_layer(id)` | Fit a layer |
| `refresh()` | Redraw |
| `start_polygon_drawing()` | Let the user draw a polygon (see below) |
| `cancel_drawing()` | Stop the drawing in progress |
| `is_drawing() -> bool` | A drawing is in progress |
| `set_marked(polygons)` / `marked()` | Thick cyan outline around each (lon, lat) polygon (the checked fields), under the hover highlight |
| `set_highlight(vertices)` / `highlighted()` | Bright outline around a (lon, lat) polygon over every layer; `None` removes it |
| `zoom_by(factor)` | Zoom around the centre: visible width × factor (0.5 = twice as close) |
| `meters_per_pixel() -> float` | Ground metres covered by one screen pixel at the centre of the view (`None` without a real map); used by the scale bar |

| Event | Arguments |
|-------|-----------|
| `cursor_moved` | `lon, lat` |
| `clicked` | `lon, lat` (QGIS: after `set_click_mode(True)`) |
| `layers_changed` | – |
| `polygon_drawn` | `vertices`: list of `(lon, lat)`, first vertex not repeated |
| `drawing_cancelled` | – |
| `layer_right_clicked` | `layer_id, lon, lat`: right click on a feature of a visible, unlocked layer; not while drawing |
| `layer_hovered` | `layer_id` or `None`, `lon, lat`: the mouse moved onto a feature of another visible, unlocked layer, or off every feature; not while dragging or drawing |
| `view_changed` | – (after a pan, zoom or resize) |
| `layer_double_clicked` | `layer_id, lon, lat`: double click on a feature of a visible, unlocked layer (topmost first), never while drawing. The map does not zoom in on that click |

The default tool (`PickPanTool`, `fieldshift/map/pick_tool.py`) pans by
dragging. A click without dragging does not recentre the map, so it does not
jump under the cursor when the user double-clicks a field.

### Drawing a polygon

`start_polygon_drawing()` switches the map to a drawing tool: each left click
adds a vertex and a preview follows the cursor. A double click, a right click
or a click on the first vertex closes the polygon (3 vertices minimum),
Backspace removes the last vertex and Esc cancels. The drawing ends with
`polygon_drawn` or `drawing_cancelled` and the map goes back to panning.

```python
view.polygon_drawn.connect(lambda vertices: print(len(vertices), "vertices"))
view.start_polygon_drawing()
```

In QGIS the tool is `PolygonDrawTool` (`fieldshift/map/polygon_tool.py`).
`PlaceholderMapView` has no map to click on: tests call
`simulate_polygon(vertices)` instead.

```python
view = create_map_view()
layer_id = view.add_layer(LayerSpec.vector("Fields", "fields.geojson"))
view.zoom_to_layer(layer_id)
view.cursor_moved.connect(lambda lon, lat: print(lon, lat))
```

## Extending the abstraction

To give the UI a new map capability (for example, "select features in a
box"):

1. Add an `@abstractmethod` to `MapView` in `view.py`, with a minidoc
   comment (arguments line + description).
2. Implement it in `QgisMapView` (`qgis_view.py`) and `PlaceholderMapView`
   (a no-op or in-memory version is fine).
3. If it notifies the UI, add an `Event` in `MapView.__init__`.
4. Add a case to the `_ViewContract` tests in
   `tests/test_map_abstraction.py`: every backend runs them.
5. `make docs`.

## Adding a backend

Subclass `MapView`, implement every abstract method, call
`super().__init__()`, and register it in `create_map_view()` in
`factory.py`. Then add a test class that inherits `_ViewContract`.
