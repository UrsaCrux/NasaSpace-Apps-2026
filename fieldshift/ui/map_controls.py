"""Buttons floating over the top-left corner of the map, top to bottom: switch
the background between satellite and street map, fit all the fields, search a
place, zoom in / out.

Uses the map only through MapView and the fields through FieldsManager.
"""

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets

# distance (pixels) from the top-left corner of the map
MARGIN_PX = 12
# how much one click on + / - zooms (visible width multiplied by this)
ZOOM_STEP = 0.5

_STYLE = """
QFrame#mapControls { background: transparent; }
QPushButton { background: rgba(255, 255, 255, 235); color: #1b1b1b; border: 1px solid #9aa39a;
              border-radius: 6px; padding: 4px 10px; font-weight: bold; }
QPushButton:hover { background: #e8f1e8; }
QPushButton:disabled { color: #9e9e9e; }
QPushButton#zoomButton { font-size: 18px; min-width: 32px; max-width: 32px;
                         min-height: 30px; max-height: 30px; padding: 0; }
QPushButton:checked { background: #2e7d32; color: white; border-color: #1b5e20; }
"""


# the floating buttons. basemaps maps "satellite" / "streets" to their layer
# ids; without both, the background switch is not shown
class MapControls(QtWidgets.QFrame):

    # (MapView view, FieldsManager fields, dict basemaps = None)
    # puts the buttons over view.widget()
    def __init__(self, view, fields, basemaps=None):
        super().__init__(view.widget())
        self.view = view
        self.fields = fields
        self.basemaps = dict(basemaps or {})
        self.setObjectName("mapControls")
        self.setStyleSheet(_STYLE)

        self.zoom_in_button = self._button("＋", tr("map.zoom_in"), lambda: view.zoom_by(ZOOM_STEP))
        self.zoom_out_button = self._button("−", tr("map.zoom_out"),
                                            lambda: view.zoom_by(1 / ZOOM_STEP))
        for button in (self.zoom_in_button, self.zoom_out_button):
            button.setObjectName("zoomButton")
        self.fit_button = self._button(tr("map.fit_fields"), tr("map.fit_fields_tooltip"),
                                       fields.zoom_to_all)
        # the magnifier opens the place search panel (ui/map_search.py), which
        # listens to this button's toggled signal
        self.search_button = self._button("🔍", tr("map.search_tooltip"), lambda: None)
        self.search_button.setObjectName("zoomButton")
        self.search_button.setCheckable(True)

        # top to bottom: background switch, "My fields", search, then + / -
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.satellite_button = self.streets_button = None
        if "satellite" in self.basemaps and "streets" in self.basemaps:
            self.satellite_button = self._button(tr("map.satellite"), tr("map.basemap_tooltip"),
                                                 lambda: self.show_basemap("satellite"))
            self.streets_button = self._button(tr("map.streets"), tr("map.basemap_tooltip"),
                                               lambda: self.show_basemap("streets"))
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(0)
            for button in (self.satellite_button, self.streets_button):
                button.setCheckable(True)
                row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
            layout.addSpacing(6)
            self.show_basemap("satellite")

        layout.addWidget(self.fit_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.search_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(6)
        layout.addWidget(self.zoom_in_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.zoom_out_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

        fields.fields_changed.connect(self._update_buttons)
        self._update_buttons()
        self.adjustSize()
        self.move(MARGIN_PX, MARGIN_PX)
        self.raise_()

    # (str key)
    # shows the "satellite" or the "streets" background and hides the other
    def show_basemap(self, key):
        for name, layer_id in self.basemaps.items():
            self.view.set_layer_visible(layer_id, name == key)
        if self.satellite_button is not None:
            self.satellite_button.setChecked(key == "satellite")
            self.streets_button.setChecked(key == "streets")

    # ()
    # "satellite" or "streets": the background shown now
    def basemap(self):
        visible = {i.id for i in self.view.layers() if i.visible}
        return next((k for k, lid in self.basemaps.items() if lid in visible), None)

    def _button(self, text, tooltip, slot):
        button = QtWidgets.QPushButton(text)
        button.setToolTip(tooltip)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)    # Esc stays with the map
        button.clicked.connect(lambda *_: slot())
        return button

    def _update_buttons(self):
        self.fit_button.setEnabled(self.fields.count() > 0)
