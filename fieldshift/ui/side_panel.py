"""Right-hand panel. Uses the map only through the MapView abstraction."""

from fieldshift import native
from fieldshift.fields.manager import FieldsManager
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui import dialogs
from fieldshift.ui.field_dialog import FieldDialog
from fieldshift.ui.field_list import EDITABLE_ROLE, LAYER_ID_ROLE, FieldList
from fieldshift.ui.fields_data import FieldsDataBox


# panel with the user's fields (and any other non-base layer), the data of
# the checked fields, cursor position and an empty "Tools" box where new
# features are meant to be added. a field's checkbox chooses it (for data,
# export, delete); for other layers it shows / hides them. base layers
# (LayerInfo.locked) stay on the map but are not listed
class SidePanel(QtWidgets.QWidget):

    # (MapView view, QWidget parent = None, FieldsManager fields = None)
    # builds the panel and subscribes to the view events; creates its own
    # FieldsManager when none is shared
    def __init__(self, view, parent=None, fields=None):
        super().__init__(parent)
        self.view = view
        self.fields = fields if fields is not None else FieldsManager(view)
        self.setMinimumWidth(280)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_layers_box())
        # data of the checked fields (see fields_data.py)
        self.data_box = FieldsDataBox(self.fields)
        layout.addWidget(self.data_box)
        layout.addWidget(self._build_position_box())
        # contributors: put new feature widgets inside this box
        self.tools_box = self._build_tools_box()
        layout.addWidget(self.tools_box)
        layout.addStretch(1)

        view.layers_changed.connect(self.refresh_layers)
        self.fields.fields_changed.connect(self.refresh_layers)
        self.fields.selection_changed.connect(self._sync_checks)
        view.cursor_moved.connect(self._on_cursor)
        view.clicked.connect(self._on_click)
        view.layer_double_clicked.connect(self._on_map_double_click)
        self.refresh_layers()

    # ()
    # rebuilds the list from view.layers(), leaving out the base layers
    def refresh_layers(self):
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for info in self.view.layers():
            if info.locked:
                continue
            text = info.name if self.fields.is_field(info.id) else f"{info.name}  [{info.kind.value}]"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(LAYER_ID_ROLE, info.id)
            item.setData(EDITABLE_ROLE, self.fields.is_field(info.id))   # Edit button
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            checked = (self.fields.is_selected(info.id) if self.fields.is_field(info.id)
                       else info.visible)
            item.setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
            self.layer_list.addItem(item)
        self.layer_list.blockSignals(False)
        self.empty_label.setVisible(self.layer_list.count() == 0)
        self._update_delete_button()

    # -- building blocks ---------------------------------------------------

    def _build_header(self):
        title = QtWidgets.QLabel(f"<h2>{tr('header.title')}</h2><p>{tr('header.subtitle')}</p>")
        title.setWordWrap(True)
        return title

    def _build_layers_box(self):
        box = QtWidgets.QGroupBox(tr("fields.list_title"))
        v = QtWidgets.QVBoxLayout(box)

        self.empty_label = QtWidgets.QLabel(tr("fields.empty"))
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #666;")
        v.addWidget(self.empty_label)

        self.layer_list = FieldList()
        self.layer_list.edit_requested.connect(self._on_edit_requested)
        self.layer_list.setToolTip(tr("fields.list_tooltip"))
        self.layer_list.itemChanged.connect(self._on_item_changed)
        self.layer_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.layer_list.itemClicked.connect(self._on_item_clicked)
        self.layer_list.currentItemChanged.connect(self._update_delete_button)
        v.addWidget(self.layer_list)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.delete_button = QtWidgets.QPushButton(tr("common.delete"))
        self.delete_button.clicked.connect(self._remove_selected)
        row.addWidget(self.delete_button)
        v.addLayout(row)
        return box

    def _build_position_box(self):
        box = QtWidgets.QGroupBox(tr("position.title"))
        form = QtWidgets.QFormLayout(box)
        self.cursor_label = QtWidgets.QLabel("–")
        self.click_label = QtWidgets.QLabel("–")
        form.addRow(tr("position.cursor"), self.cursor_label)
        form.addRow(tr("position.last_click"), self.click_label)
        return box

    def _build_tools_box(self):
        box = QtWidgets.QGroupBox(tr("tools.title"))
        v = QtWidgets.QVBoxLayout(box)
        status = (tr("tools.native_loaded", version=native.version()) if native.is_available()
                  else tr("tools.native_missing"))
        v.addWidget(QtWidgets.QLabel(status))
        return box

    # -- slots -------------------------------------------------------------

    # ()
    # what Delete acts on: the checked fields, else the highlighted row
    def _delete_targets(self):
        checked = self.fields.selected()
        if checked:
            return checked
        item = self.layer_list.currentItem()
        return [item.data(LAYER_ID_ROLE)] if item is not None else []

    def _remove_selected(self):
        targets = self._delete_targets()
        fields = [i for i in targets if self.fields.is_field(i)]
        for layer_id in targets:
            if layer_id not in fields:
                self.view.remove_layer(layer_id)      # not a field: no file to lose
        if not fields:
            return
        if len(fields) == 1:
            text = tr("fields.remove_confirm", name=self.fields.field(fields[0]).name)
        else:
            text = tr("fields.remove_many_confirm", count=len(fields))
        if dialogs.confirm(self, tr("fields.remove_title"), text,
                           tr("common.delete"), danger=True):
            for layer_id in fields:
                self.fields.remove(layer_id)

    # ticks the checkboxes of the chosen fields in place (no rebuild)
    def _sync_checks(self):
        self.layer_list.blockSignals(True)
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            layer_id = item.data(LAYER_ID_ROLE)
            if self.fields.is_field(layer_id):
                checked = self.fields.is_selected(layer_id)
                item.setCheckState(QtCore.Qt.CheckState.Checked if checked
                                   else QtCore.Qt.CheckState.Unchecked)
        self.layer_list.blockSignals(False)
        self._update_delete_button()

    def _update_delete_button(self, *_):
        self.delete_button.setEnabled(bool(self._delete_targets()))

    # Qt is still handling the click on this item: never rebuild the list
    # here (that deletes the item and crashes), only record the change
    def _on_item_changed(self, item):
        layer_id = item.data(LAYER_ID_ROLE)
        checked = item.checkState() == QtCore.Qt.CheckState.Checked
        self._checkbox_clicked = True
        QtCore.QTimer.singleShot(0, self._forget_checkbox_click)
        if self.fields.is_field(layer_id):
            self.fields.set_selected(layer_id, checked)
        else:
            QtCore.QTimer.singleShot(0, lambda: self.view.set_layer_visible(layer_id, checked))

    def _forget_checkbox_click(self):
        self._checkbox_clicked = False

    def _on_item_double_clicked(self, item):
        if item is not None:
            self.view.zoom_to_layer(item.data(LAYER_ID_ROLE))

    # a click on the name zooms to the field; a click on the checkbox does not
    def _on_item_clicked(self, item):
        if item is None or getattr(self, "_checkbox_clicked", False):
            return
        layer_id = item.data(LAYER_ID_ROLE)
        if self.fields.is_field(layer_id):
            self.fields.zoom_to(layer_id)

    # the Edit button of a field row was clicked. the dialog opens once Qt has
    # finished handling the click: saving rebuilds the list
    def _on_edit_requested(self, layer_id):
        QtCore.QTimer.singleShot(0, lambda: self._edit_field(layer_id))

    # (str layer_id)
    # asks for the new details of a field and applies them
    def _edit_field(self, layer_id):
        field = self.fields.field(layer_id)
        if field is None or self.view.is_drawing():
            return
        dialog = FieldDialog(self.fields.store, field=field, parent=self.window())
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        try:
            new_id = self.fields.update(layer_id, dialog.name(), dialog.color(), dialog.data())
        except (ValueError, OSError) as exc:
            dialogs.inform(self, tr("fields.title"), tr("fields.save_failed", error=exc))
            return
        self._highlight(new_id)

    # (str layer_id)
    # makes the row of this layer the current one
    def _highlight(self, layer_id):
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            if item.data(LAYER_ID_ROLE) == layer_id:
                self.layer_list.setCurrentItem(item)
                self.layer_list.scrollToItem(item)
                return

    # double click on a field in the map: tick its checkbox (or untick it if
    # it was ticked) and highlight its row. other layers and clicks made
    # while drawing are ignored
    def _on_map_double_click(self, layer_id, lon, lat):
        if self.view.is_drawing() or not self.fields.is_field(layer_id):
            return
        self.fields.set_selected(layer_id, not self.fields.is_selected(layer_id))
        self._highlight(layer_id)

    def _on_cursor(self, lon, lat):
        self.cursor_label.setText(f"{lon:.5f}, {lat:.5f}")

    def _on_click(self, lon, lat):
        self.click_label.setText(f"{lon:.5f}, {lat:.5f}")
