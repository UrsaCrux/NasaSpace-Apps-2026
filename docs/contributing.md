# Contributing

## Workflow

1. Work on a branch, keep commits small.
2. Document every public declaration with a minidoc comment
   ([minidoc.md](minidoc.md)).
3. `make test` and `make docs`, commit the regenerated `docs/api/`.

## Adding a feature to the side panel

The panel has an empty **Tools** box (`SidePanel.tools_box`) meant for new
features. Typical pattern, e.g. a "distance between two clicks" tool:

```python
# fieldshift/ui/tools/distance.py
from fieldshift import native
from fieldshift.qt import QtWidgets


# measures the distance between the last two clicks on the map
class DistanceTool(QtWidgets.QWidget):

    # (MapView view)
    # subscribes to clicks on the view
    def __init__(self, view):
        super().__init__()
        self.points = []
        self.label = QtWidgets.QLabel("Click two points")
        QtWidgets.QVBoxLayout(self).addWidget(self.label)
        view.clicked.connect(self._on_click)

    def _on_click(self, lon, lat):
        self.points = (self.points + [(lat, lon)])[-2:]
        if len(self.points) == 2:
            km = native.haversine_km(*self.points[0], *self.points[1])
            self.label.setText(f"{km:.1f} km")
```

and in `SidePanel.__init__`: `self.tools_box.layout().addWidget(DistanceTool(view))`.

Texts the user reads go in `fieldshift/i18n/*.json` and are read with
`tr("key")` ([i18n.md](i18n.md)); the example above writes them inline only
to stay short.

Talk to the map only through `MapView`. If you need something it does not
offer, extend the abstraction first ([map-abstraction.md](map-abstraction.md)).

## Adding a C++ function

See [`cpp/README.md`](../cpp/README.md): declare in the header, define in
`src/`, bind in `fieldshift/native/__init__.py`, add a test in
`tests/test_native.py`.

## Tests

```bash
make test
```

- Tests run headless (`QT_QPA_PLATFORM=offscreen`).
- `tests/test_map_abstraction.py` runs the same contract against every map
  backend; QGIS tests are skipped when QGIS is missing.
- `tests/test_native.py` is skipped until `make cpp` has been run.
