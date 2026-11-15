"""Keeps the saved fields and their map layers in sync. No widgets here."""

import sys

from fieldshift.fields.store import FieldStore
from fieldshift.map.events import Event
from fieldshift.map.layer import LayerSpec

# look of fields on the map: the field's colour with a semi-transparent fill
# (alpha 0x55, "#AARRGGBB") and a solid, darker outline
FIELD_FILL_ALPHA = "55"
FIELD_STROKE_DARKER = 0.6   # outline channels = colour channels * this
FIELD_STROKE_WIDTH = 0.8    # millimetres

# name drawn over each field: white text with a dark halo (readable on satellite)
LABEL_COLOR = "#ffffff"
LABEL_HALO = "#1b1b1b"

# MapView render group of the field layers (see the "render_group" option)
FIELDS_RENDER_GROUP = "fields"

# extra space around a field when zooming to it (fraction of its size)
ZOOM_MARGIN = 0.25


# (str color)
# (fill, stroke) CSS colours of a field on the map: "#rrggbb" becomes a
# semi-transparent "#AARRGGBB" fill and a darker "#rrggbb" outline
def style_colors(color):
    rgb = color.lstrip("#")
    dark = "".join(f"{int(int(rgb[i:i + 2], 16) * FIELD_STROKE_DARKER):02x}" for i in (0, 2, 4))
    return f"#{FIELD_FILL_ALPHA}{rgb}", f"#{dark}"


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
        # emitted with (str layer_id) after a field's records change
        self.records_changed = Event()
        self._fields = {}          # layer id -> Field
        self._selected = set()     # layer ids of the fields the user checked
        # the map outlines the checked fields
        self.selection_changed.connect(self._show_marks)
        self.fields_changed.connect(self._show_marks)
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

    # (str name, list vertices, str color = None, dict data = None)
    # saves a new field and shows it on the map; returns its layer id.
    # raises ValueError (bad name or polygon, layer cannot load) or OSError
    def add(self, name, vertices, color=None, data=None):
        field = self.store.create(name, vertices, color=color, data=data)
        try:
            layer_id = self._show(field)
        except ValueError:
            self.store.delete(field.name)
            raise
        self.fields_changed.emit()
        return layer_id

    # (str layer_id, str name, str color = None, dict data = None)
    # changes name, colour and data of a field: the file, the map layer and
    # the lists follow, and the field stays checked if it was. the layer gets a
    # new id, which is returned. raises ValueError (not a field, bad name,
    # layer cannot load) or OSError; then nothing has changed
    def update(self, layer_id, name, color=None, data=None):
        old = self._fields.get(layer_id)
        if old is None:
            raise ValueError(f"layer {layer_id!r} is not a field")
        new = self.store.update(old.name, name, color, data)
        edits = _edited_records(old.data, new.data)
        if edits:                            # values typed in "Edit field" go to the records
            new = self.store.save_records(new.name, new.records + edits)
        try:
            new_id = self._show(new)
        except ValueError:
            self.store.update(new.name, old.name, old.color, old.data)     # undo
            raise
        was_selected = layer_id in self._selected
        del self._fields[layer_id]
        self._selected.discard(layer_id)
        if was_selected:
            self._selected.add(new_id)
        self.view.remove_layer(layer_id)
        self.fields_changed.emit()
        return new_id

    # (str layer_id)
    # the records (fields.records.Record) of a field, oldest first
    def records(self, layer_id):
        field = self._fields.get(layer_id)
        return field.records if field else ()

    # (str layer_id, Record record)
    # adds a measurement or event to a field (saved in its file). a kind that
    # is also a datum (pH, nitrogen, ...) becomes the field's datum when it is
    # the newest of its kind
    def add_record(self, layer_id, record):
        field = self._fields[layer_id]
        records = tuple(sorted(field.records + (record,), key=lambda r: r.time))
        self._save_records(layer_id, records)

    # (str layer_id, Record record)
    # removes a record of a field
    def remove_record(self, layer_id, record):
        field = self._fields[layer_id]
        self._save_records(layer_id, tuple(r for r in field.records if r != record))

    def _save_records(self, layer_id, records):
        from fieldshift.fields.records import KINDS, latest
        field = self._fields[layer_id]
        data = {k: dict(v) if isinstance(v, dict) else v for k, v in field.data.items()}
        for kind, (_, _, key, _) in KINDS.items():
            newest = latest(records, kind) if key else None
            if newest is not None and newest.value is not None and key in data:
                data[key] = {**data[key], "value": newest.value, "source": "user"}
        self._fields[layer_id] = self.store.save_records(field.name, records, data)
        self.records_changed.emit(layer_id)

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
        if field is not None:
            self._zoom_to_vertices(field.vertices)

    # ()
    # fits the map to all the fields at once (does nothing without fields);
    # returns True when it moved the map
    def zoom_to_all(self):
        vertices = [v for f in self._fields.values() for v in f.vertices]
        if not vertices:
            return False
        self._zoom_to_vertices(vertices)
        return True

    def _zoom_to_vertices(self, vertices):
        lons = [v[0] for v in vertices]
        lats = [v[1] for v in vertices]
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

    # outlines the checked fields on the map
    def _show_marks(self):
        self.view.set_marked([self._fields[i].vertices for i in self.selected()])

    def _show(self, field):
        fill, stroke = style_colors(field.color)
        spec = LayerSpec.vector(field.name, str(field.path), fill_color=fill,
                                stroke_color=stroke, stroke_width=FIELD_STROKE_WIDTH,
                                label_field="name", label_color=LABEL_COLOR,
                                label_halo_color=LABEL_HALO,
                                # all fields drawn as one picture: one map-sized
                                # image per field used gigabytes with many fields
                                render_group=FIELDS_RENDER_GROUP)
        layer_id = self.view.add_layer(spec)
        self._fields[layer_id] = field
        return layer_id


# (dict old, dict new)
# Records for the data values the user typed or changed in "Edit field"
def _edited_records(old, new):
    from fieldshift.fields.records import EDITED, KINDS, Record, now
    time, records = now(), []
    for kind, (_, _, key, _) in KINDS.items():
        if not key:
            continue
        before = ((old or {}).get(key) or {}).get("value")
        item = (new or {}).get(key) or {}
        if item.get("source") == "user" and item.get("value") is not None \
                and item["value"] != before:
            records.append(Record(time, kind, float(item["value"]), origin=EDITED))
    return tuple(records)
