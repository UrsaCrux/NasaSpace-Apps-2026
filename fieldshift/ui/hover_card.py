"""Card that follows the mouse while it is over a field on the map: name,
area, crop and a few zone data. The field's outline is highlighted meanwhile.

Uses the map only through MapView (layer_hovered, set_highlight) and the
fields through FieldsManager.
"""

from fieldshift.crops import label as crop_label
from fieldshift.fields.schema import CROP_KEY, DATA_FIELDS
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.ui.field_dialog import data_label, format_value

# zone data shown on the card, in this order, when the field has them
CARD_KEYS = ("elevation", "slope", "actual_et", "ndvi")
# distance (pixels) between the mouse and the card
OFFSET_PX = 16

_SPECS = {spec.key: spec for spec in DATA_FIELDS}


# the floating card; hidden while the mouse is not over a field
class HoverCard(QtWidgets.QFrame):

    # (MapView view, FieldsManager fields)
    # puts the (hidden) card over view.widget() and follows the mouse
    def __init__(self, view, fields):
        super().__init__(view.widget())
        self.view = view
        self.fields = fields
        self.layer_id = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setObjectName("hoverCard")
        self.setStyleSheet(
            "QFrame#hoverCard { background: rgba(255, 255, 255, 240); border: 1px solid #9aa39a;"
            " border-radius: 8px; } QLabel { background: transparent; border: none; }")
        self.title_label = QtWidgets.QLabel()
        self.info_label = QtWidgets.QLabel()
        self.info_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.hint_label = QtWidgets.QLabel(tr("hover.hint"))
        self.hint_label.setStyleSheet("color: #777; font-size: 11px;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)
        layout.addWidget(self.hint_label)
        self.hide()

        view.layer_hovered.connect(self._on_hovered)
        view.cursor_moved.connect(lambda *_: self._follow_mouse())
        fields.fields_changed.connect(self._on_fields_changed)

    # (str layer_id)
    # shows the card for this field (None or a non-field layer hides it)
    def show_field(self, layer_id):
        field = self.fields.field(layer_id) if layer_id is not None else None
        if field is None:
            self.layer_id = None
            self.view.set_highlight(None)
            self.hide()
            return
        self.layer_id = layer_id
        self.view.set_highlight(field.vertices)
        self.title_label.setText(
            f"<span style='color:{field.color}; font-size:15px'>■</span> <b>{field.name}</b>")
        lines = [tr("hover.area", area=f"{field.area_ha:.2f}")]
        crop = field.data.get(CROP_KEY, {}).get("value")
        lines.append(f"{tr('hover.crop')}: {crop_label(crop) if crop else tr('hover.no_crop')}")
        for key in CARD_KEYS:
            value = field.data.get(key, {}).get("value")
            if key in _SPECS and value is not None:
                lines.append(f"{data_label(key)}: <b>{format_value(_SPECS[key], value)}</b>")
        self.info_label.setText("<br>".join(lines))
        self.adjustSize()
        self._follow_mouse()
        self.show()
        self.raise_()

    def _on_hovered(self, layer_id, lon, lat):
        self.show_field(layer_id)

    def _on_fields_changed(self):
        if self.layer_id is not None and not self.fields.is_field(self.layer_id):
            self.show_field(None)

    # puts the card next to the mouse, inside the map
    def _follow_mouse(self):
        if self.isHidden() and self.layer_id is None:
            return
        parent = self.parentWidget()
        mouse = parent.mapFromGlobal(QtGui.QCursor.pos())
        x, y = mouse.x() + OFFSET_PX, mouse.y() + OFFSET_PX
        if x + self.width() > parent.width():             # flip to the left
            x = mouse.x() - OFFSET_PX - self.width()
        if y + self.height() > parent.height():           # flip above
            y = mouse.y() - OFFSET_PX - self.height()
        self.move(max(0, x), max(0, y))
