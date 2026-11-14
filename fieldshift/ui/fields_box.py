"""Fields box: draw, save, zoom to, remove and export the user's fields.

Uses the map only through MapView and saves fields with FieldStore. Every
text comes from fieldshift/i18n/<language>.json.
"""

import sys
from pathlib import Path

from fieldshift.fields import FieldStore
from fieldshift.i18n import tr
from fieldshift.map import Event, LayerSpec
from fieldshift.qt import QtWidgets

# look of saved fields on the map: semi-transparent fill (#AARRGGBB), solid outline
FIELD_FILL = "#5543a047"
FIELD_STROKE = "#1b5e20"
FIELD_STROKE_WIDTH = 0.8   # millimetres

# extra space around a field when zooming to it (fraction of its size)
ZOOM_MARGIN = 0.25


# dialog asking for the name of a new field: required, unique, pre-filled
# with the next free "Field N"
class FieldNameDialog(QtWidgets.QDialog):

    # (FieldStore store, QWidget parent = None)
    # builds the dialog; Save stays disabled while the name is not valid
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("fields.save_title"))
        self.setMinimumWidth(320)

        self.name_edit = QtWidgets.QLineEdit(store.suggest_name(tr("fields.default_name")))
        self.name_edit.selectAll()
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        Buttons = QtWidgets.QDialogButtonBox.StandardButton
        buttons = QtWidgets.QDialogButtonBox(Buttons.Save | Buttons.Cancel)
        self.save_button = buttons.button(Buttons.Save)
        self.save_button.setText(tr("common.save"))
        buttons.button(Buttons.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QtWidgets.QFormLayout(self)
        form.addRow(tr("fields.name_label"), self.name_edit)
        form.addRow(self.error_label)
        form.addRow(buttons)

        self.name_edit.textChanged.connect(self._validate)
        self._validate()

    # ()
    # the name typed, without surrounding spaces
    def name(self):
        return self.name_edit.text().strip()

    def _validate(self):
        problem = self.store.name_problem(self.name_edit.text())
        messages = {"empty": tr("fields.error_empty"),
                    "duplicate": tr("fields.error_duplicate", name=self.name())}
        self.error_label.setText(messages.get(problem, ""))
        self.save_button.setEnabled(problem is None)


# panel box with the "Draw field" and "Export fields…" buttons. Shows every
# saved field as a map layer and remembers which layers are fields
class FieldsBox(QtWidgets.QGroupBox):

    # (MapView view, FieldStore store = None, QWidget parent = None)
    # builds the box and loads the fields saved in earlier sessions
    def __init__(self, view, store=None, parent=None):
        super().__init__(tr("fields.title"), parent)
        self.view = view
        self.store = store if store is not None else FieldStore()
        # emitted with no arguments after a field is added or removed
        self.fields_changed = Event()
        self._fields = {}          # layer id -> Field

        self.draw_button = QtWidgets.QPushButton(tr("fields.draw"))
        self.draw_button.setCheckable(True)
        self.draw_button.clicked.connect(self._on_draw_clicked)
        self.hint_label = QtWidgets.QLabel(tr("fields.hint"))
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #555; font-size: 11px;")
        self.export_button = QtWidgets.QPushButton(tr("fields.export"))
        self.export_button.clicked.connect(lambda: self._on_export_clicked())

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.draw_button)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.export_button)

        view.polygon_drawn.connect(self._on_polygon_drawn)
        view.drawing_cancelled.connect(self._show_drawing_state)
        for field in self.store.fields():
            self._add_field_layer(field, interactive=False)
        self._update_export_button()
        self._show_drawing_state()

    # (str layer_id)
    # True when the layer is a saved field
    def is_field(self, layer_id):
        return layer_id in self._fields

    # (str layer_id)
    # the Field shown by this layer, or None
    def field(self, layer_id):
        return self._fields.get(layer_id)

    # (str layer_id)
    # centres and zooms the map on a field, with some margin around it
    def zoom_to_field(self, layer_id):
        field = self._fields.get(layer_id)
        if field is None:
            return
        lons = [v[0] for v in field.vertices]
        lats = [v[1] for v in field.vertices]
        dx = (max(lons) - min(lons)) * ZOOM_MARGIN or 0.001
        dy = (max(lats) - min(lats)) * ZOOM_MARGIN or 0.001
        self.view.zoom_to_extent(min(lons) - dx, min(lats) - dy,
                                 max(lons) + dx, max(lats) + dy)

    # (str layer_id, bool confirm = True)
    # removes a field from the map, the layer list and disk, after asking
    # when confirm is True; returns True when it was removed
    def remove_field(self, layer_id, confirm=True):
        field = self._fields.get(layer_id)
        if field is None or (confirm and not self._confirm_remove(field.name)):
            return False
        del self._fields[layer_id]
        self.view.remove_layer(layer_id)
        self.store.delete(field.name)
        self._update_export_button()
        self.fields_changed.emit()
        return True

    # (str path)
    # writes every saved field to one GeoJSON file; returns how many.
    # raises OSError when the file cannot be written
    def export_fields(self, path):
        return self.store.export(path)

    # -- slots -------------------------------------------------------------

    def _on_draw_clicked(self, checked):
        if checked:
            self.view.start_polygon_drawing()
        else:
            self.view.cancel_drawing()
        self._show_drawing_state()

    def _on_polygon_drawn(self, vertices):
        self._show_drawing_state()
        name = self._ask_name()
        if not name:
            return                      # Cancel: the drawing is discarded
        try:
            field = self.store.create(name, vertices)
        except (ValueError, OSError) as exc:
            self._warn(tr("fields.save_failed", error=exc))
            return
        self._add_field_layer(field)

    def _on_export_clicked(self):
        default = str(Path.home() / tr("fields.export_default_file"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("fields.export_title"), default, tr("fields.export_filter"))
        if not path:
            return
        if not path.lower().endswith((".geojson", ".json")):
            path += ".geojson"
        try:
            count = self.export_fields(path)
        except OSError as exc:
            self._warn(tr("fields.export_failed", error=exc))
            return
        QtWidgets.QMessageBox.information(self, tr("fields.export_title"),
                                          tr("fields.export_done", count=count, path=path))

    # -- helpers -----------------------------------------------------------

    # (Field field, bool interactive = True)
    # loads a saved field as a map layer; on failure warns (dialog when
    # interactive, stderr at start-up) and returns None
    def _add_field_layer(self, field, interactive=True):
        spec = LayerSpec.vector(field.name, str(field.path), fill_color=FIELD_FILL,
                                stroke_color=FIELD_STROKE, stroke_width=FIELD_STROKE_WIDTH)
        try:
            layer_id = self.view.add_layer(spec)
        except ValueError as exc:
            if interactive:
                self.store.delete(field.name)
                self._warn(tr("fields.save_failed", error=exc))
            else:
                print(f"warning: cannot show field {field.name!r}: {exc}", file=sys.stderr)
            return None
        self._fields[layer_id] = field
        self._update_export_button()
        self.fields_changed.emit()
        return layer_id

    def _show_drawing_state(self):
        drawing = self.view.is_drawing()
        self.draw_button.setChecked(drawing)
        self.draw_button.setText(tr("fields.drawing") if drawing else tr("fields.draw"))
        self.hint_label.setVisible(drawing)

    def _update_export_button(self):
        self.export_button.setEnabled(bool(self._fields))

    def _ask_name(self):
        dialog = FieldNameDialog(self.store, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dialog.name()
        return None

    def _confirm_remove(self, name):
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setWindowTitle(tr("fields.remove_title"))
        box.setText(tr("fields.remove_confirm", name=name))
        remove = box.addButton(tr("common.remove"),
                               QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(tr("common.cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is remove

    def _warn(self, message):
        QtWidgets.QMessageBox.warning(self, tr("fields.title"), message)
