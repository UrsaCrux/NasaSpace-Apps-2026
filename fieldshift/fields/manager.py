"""Keeps the saved fields and their map layers in sync. No widgets here."""

import sys

from fieldshift.fields.store import FieldStore
from fieldshift.map.events import Event
from fieldshift.map.layer import LayerSpec

# look of fields on the map: semi-transparent fill (#AARRGGBB), solid outline
FIELD_FILL = "#5543a047"
FIELD_STROKE = "#1b5e20"
FIELD_STROKE_WIDTH = 0.8   # millimetres

# name drawn over each field: white text with a dark halo (readable on satellite)
LABEL_COLOR = "#ffffff"
LABEL_HALO = "#1b1b1b"

# extra space around a field when zooming to it (fraction of its size)
ZOOM_MARGIN = 0.25


# the user's fields: saves them with a FieldStore and shows each one as a
# MapView layer. the UI (fields bar, side panel, future field sheets) shares
# one FieldsManager
class FieldsManager:

    # (MapView view, FieldStore store = None)
    # loads the fields saved in earlier sessions onto the map
    def __init__(self, view, store=None):
        self.view = view
        self.store = store if store is not None else FieldStore()
        # emitted with no arguments after a field is added or removed
        self.fields_changed = Event()
        # emitted with no arguments when the set of chosen fields changes
        self.selection_changed = Event()
        self._fields = {}          # layer id -> Field
        self._selected = set()     # layer ids of the fields the user checked
        for field in self.store.fields():
            try:
                self._show(field)
            except ValueError as exc:
                print(f"warning: cannot show field {field.name!r}: {exc}", file=sys.stderr)

    # ()
    # how many fields are on the map
    def count(self):
        return len(self._fields)

    # (str layer_id)
    # True when the layer is a saved field
    def is_field(self, layer_id):
        return layer_id in self._fields

    # (str layer_id)
    # the Field shown by this layer, or None
    def field(self, layer_id):
        return self._fields.get(layer_id)

    # ()
    # layer ids of every field, oldest first
    def layer_ids(self):
        return list(self._fields)

    # ()
    # layer ids of the fields the user chose, oldest first
    def selected(self):
        return [i for i in self._fields if i in self._selected]

    # (str layer_id)
    # True when the user chose this field
    def is_selected(self, layer_id):
        return layer_id in self._selected

    # (str layer_id, bool selected)
    # adds a field to the chosen ones or takes it out
    def set_selected(self, layer_id, selected):
        if layer_id not in self._fields or (layer_id in self._selected) == selected:
            return
        if selected:
            self._selected.add(layer_id)
        else:
            self._selected.discard(layer_id)
        self.selection_changed.emit()

    # (str name, list vertices)
    # saves a new field and shows it on the map; returns its layer id.
    # raises ValueError (bad name or polygon, layer cannot load) or OSError
    def add(self, name, vertices):
        field = self.store.create(name, vertices)
        try:
            layer_id = self._show(field)
        except ValueError:
            self.store.delete(field.name)
            raise
        self.fields_changed.emit()
        return layer_id

    # (str layer_id)
    # removes a field from the map and deletes its file; returns False when
    # the layer is not a field
    def remove(self, layer_id):
        field = self._fields.pop(layer_id, None)
        if field is None:
            return False
        was_selected = layer_id in self._selected
        self._selected.discard(layer_id)
        self.view.remove_layer(layer_id)
        self.store.delete(field.name)
        self.fields_changed.emit()
        if was_selected:
            self.selection_changed.emit()
        return True

    # (str layer_id)
    # centres and zooms the map on a field, with some margin around it
    def zoom_to(self, layer_id):
        field = self._fields.get(layer_id)
        if field is None:
            return
        lons = [v[0] for v in field.vertices]
        lats = [v[1] for v in field.vertices]
        dx = (max(lons) - min(lons)) * ZOOM_MARGIN or 0.001
        dy = (max(lats) - min(lats)) * ZOOM_MARGIN or 0.001
        self.view.zoom_to_extent(min(lons) - dx, min(lats) - dy,
                                 max(lons) + dx, max(lats) + dy)

    # (str path, list layer_ids = None)
    # writes these fields (all when None) to one GeoJSON file; returns how
    # many. raises OSError
    def export(self, path, layer_ids=None):
        names = None if layer_ids is None else [
            self._fields[i].name for i in layer_ids if i in self._fields]
        return self.store.export(path, names)

    def _show(self, field):
        spec = LayerSpec.vector(field.name, str(field.path), fill_color=FIELD_FILL,
                                stroke_color=FIELD_STROKE, stroke_width=FIELD_STROKE_WIDTH,
                                label_field="name", label_color=LABEL_COLOR,
                                label_halo_color=LABEL_HALO)
        layer_id = self.view.add_layer(spec)
        self._fields[layer_id] = field
        return layer_id
