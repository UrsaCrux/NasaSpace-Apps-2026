"""Right-hand panel. Uses the map only through the MapView abstraction."""

import os

from fieldshift import native
from fieldshift.map import LayerKind, LayerSpec
from fieldshift.qt import QtCore, QtWidgets

# file dialog filters per layer kind
VECTOR_FILTER = "Vector files (*.geojson *.json *.shp *.gpkg *.kml);;All files (*)"
RASTER_FILTER = "Raster files (*.tif *.tiff *.nc *.hdf *.img);;All files (*)"

# role used to store the layer id on each list item
LAYER_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole


# panel with the layer list, layer actions, cursor position and an empty
# "Tools" box where new features are meant to be added
class SidePanel(QtWidgets.QWidget):

    # (MapView view, QWidget parent = None)
    # builds the panel and subscribes to the view events
    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
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
        view.cursor_moved.connect(self._on_cursor)
        view.clicked.connect(self._on_click)
        self.refresh_layers()

    # ()
    # rebuilds the layer list from view.layers()
    def refresh_layers(self):
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for info in self.view.layers():
            item = QtWidgets.QListWidgetItem(f"{info.name}  [{info.kind.value}]")
            item.setData(LAYER_ID_ROLE, info.id)
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if info.visible else QtCore.Qt.CheckState.Unchecked)
            self.layer_list.addItem(item)
        self.layer_list.blockSignals(False)

    # -- building blocks ---------------------------------------------------

    def _build_header(self):
        title = QtWidgets.QLabel("<h2>farmer-shit</h2>"
                                 "<p>Program to adapt farmers with NASA data</p>")
        title.setWordWrap(True)
        return title

    def _build_layers_box(self):
        box = QtWidgets.QGroupBox("Layers")
        v = QtWidgets.QVBoxLayout(box)

        self.layer_list = QtWidgets.QListWidget()
        self.layer_list.itemChanged.connect(self._on_item_changed)
        self.layer_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        v.addWidget(self.layer_list)

        row = QtWidgets.QHBoxLayout()
        for text, slot in (("Add vector…", self._add_vector),
                           ("Add raster…", self._add_raster),
                           ("Remove", self._remove_selected)):
            button = QtWidgets.QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
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

    def _add_vector(self):
        self._add_from_file(LayerKind.VECTOR, VECTOR_FILTER)

    def _add_raster(self):
        self._add_from_file(LayerKind.RASTER, RASTER_FILTER)

    def _add_from_file(self, kind, file_filter):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open layer", "", file_filter)
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        spec = (LayerSpec.vector if kind is LayerKind.VECTOR else LayerSpec.raster)(name, path)
        try:
            layer_id = self.view.add_layer(spec)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Cannot open layer", str(exc))
            return
        self.view.zoom_to_layer(layer_id)

    def _remove_selected(self):
        item = self.layer_list.currentItem()
        if item is not None:
            self.view.remove_layer(item.data(LAYER_ID_ROLE))

    def _on_item_changed(self, item):
        visible = item.checkState() == QtCore.Qt.CheckState.Checked
        self.view.set_layer_visible(item.data(LAYER_ID_ROLE), visible)

    def _on_item_double_clicked(self, item):
        self.view.zoom_to_layer(item.data(LAYER_ID_ROLE))

    def _on_cursor(self, lon, lat):
        self.cursor_label.setText(f"{lon:.5f}, {lat:.5f}")

    def _on_click(self, lon, lat):
        self.click_label.setText(f"{lon:.5f}, {lat:.5f}")
