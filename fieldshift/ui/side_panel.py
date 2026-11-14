"""Right-hand panel. Uses the map only through the MapView abstraction."""

from fieldshift import native
from fieldshift.fields.manager import FieldsManager
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui import dialogs

# role used to store the layer id on each list item
LAYER_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole


# panel with the user's fields (and any other non-base layer), cursor
# position and an empty "Tools" box where new features are meant to be added.
# base layers (LayerInfo.locked) stay on the map but are not listed
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
        layout.addWidget(self._build_position_box())
        # contributors: put new feature widgets inside this box
        self.tools_box = self._build_tools_box()
        layout.addWidget(self.tools_box)
        layout.addStretch(1)

        view.layers_changed.connect(self.refresh_layers)
        self.fields.fields_changed.connect(self.refresh_layers)
        view.cursor_moved.connect(self._on_cursor)
        view.clicked.connect(self._on_click)
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
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if info.visible else QtCore.Qt.CheckState.Unchecked)
            self.layer_list.addItem(item)
        self.layer_list.blockSignals(False)
        self.empty_label.setVisible(self.layer_list.count() == 0)
        self._update_delete_button()

    # -- building blocks ---------------------------------------------------

    def _build_header(self):
        title = QtWidgets.QLabel("<h2>farmer-shit</h2>"
                                 "<p>Program to adapt farmers with NASA data</p>")
        title.setWordWrap(True)
        return title

    def _build_layers_box(self):
        box = QtWidgets.QGroupBox(tr("fields.list_title"))
        v = QtWidgets.QVBoxLayout(box)

        self.empty_label = QtWidgets.QLabel(tr("fields.empty"))
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #666;")
        v.addWidget(self.empty_label)

        self.layer_list = QtWidgets.QListWidget()
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
        box = QtWidgets.QGroupBox("Position")
        form = QtWidgets.QFormLayout(box)
        self.cursor_label = QtWidgets.QLabel("–")
        self.click_label = QtWidgets.QLabel("–")
        form.addRow("Cursor:", self.cursor_label)
        form.addRow("Last click:", self.click_label)
        return box

    def _build_tools_box(self):
        box = QtWidgets.QGroupBox("Tools")
        v = QtWidgets.QVBoxLayout(box)
        status = (f"C++ core {native.version()} loaded" if native.is_available()
                  else "C++ core not built (see cpp/README.md)")
        v.addWidget(QtWidgets.QLabel(status))
        return box

    # -- slots -------------------------------------------------------------

    def _remove_selected(self):
        item = self.layer_list.currentItem()
        if item is None:
            return
        layer_id = item.data(LAYER_ID_ROLE)
        field = self.fields.field(layer_id)
        if field is None:
            self.view.remove_layer(layer_id)
        elif dialogs.confirm(self, tr("fields.remove_title"),
                             tr("fields.remove_confirm", name=field.name),
                             tr("common.delete"), danger=True):
            self.fields.remove(layer_id)

    def _update_delete_button(self, *_):
        self.delete_button.setEnabled(self.layer_list.currentItem() is not None)

    def _on_item_changed(self, item):
        visible = item.checkState() == QtCore.Qt.CheckState.Checked
        self.view.set_layer_visible(item.data(LAYER_ID_ROLE), visible)

    def _on_item_double_clicked(self, item):
        self.view.zoom_to_layer(item.data(LAYER_ID_ROLE))

    def _on_item_clicked(self, item):
        layer_id = item.data(LAYER_ID_ROLE)
        if self.fields.is_field(layer_id):
            self.fields.zoom_to(layer_id)

    def _on_cursor(self, lon, lat):
        self.cursor_label.setText(f"{lon:.5f}, {lat:.5f}")

    def _on_click(self, lon, lat):
        self.click_label.setText(f"{lon:.5f}, {lat:.5f}")
