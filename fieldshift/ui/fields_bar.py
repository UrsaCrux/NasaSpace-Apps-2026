"""Bar under the map: "Draw field" on the left, "Export fields…" on the right.

Uses the map only through MapView and the fields through FieldsManager.
Every text comes from fieldshift/i18n/<language>.json.
"""

from pathlib import Path

from fieldshift.i18n import tr
from fieldshift.qt import QtWidgets
from fieldshift.ui import dialogs
from fieldshift.ui.field_dialog import FieldDialog

# look of the bar and of its main button
BAR_STYLE = """
QFrame#fieldsBar { background: #f4f6f4; border-top: 1px solid #c9d1c9; }
QPushButton#drawField { background: #2e7d32; color: white; border: none;
                        border-radius: 4px; padding: 6px 16px; font-weight: bold; }
QPushButton#drawField:hover { background: #276b2b; }
QPushButton#drawField:checked { background: #f9a825; color: #222; }
QLabel#drawHint { color: #444; }
"""


# bar placed under the map: draws new fields and exports the checked ones
# (all of them when none is checked)
class FieldsBar(QtWidgets.QFrame):

    # (MapView view, FieldsManager fields, QWidget parent = None)
    # builds the bar and listens to the drawing events of the view
    def __init__(self, view, fields, parent=None):
        super().__init__(parent)
        self.view = view
        self.fields = fields
        self.setObjectName("fieldsBar")
        self.setStyleSheet(BAR_STYLE)

        self.draw_button = QtWidgets.QPushButton(tr("fields.draw"))
        self.draw_button.setObjectName("drawField")
        self.draw_button.setCheckable(True)
        self.draw_button.clicked.connect(self._on_draw_clicked)
        self.hint_label = QtWidgets.QLabel(tr("fields.hint"))
        self.hint_label.setObjectName("drawHint")
        self.hint_label.setWordWrap(True)
        self.export_button = QtWidgets.QPushButton(tr("fields.export_all"))
        self.export_button.clicked.connect(lambda: self._on_export_clicked())

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.addWidget(self.draw_button)
        row.addWidget(self.hint_label, 1)
        row.addStretch(0)
        row.addWidget(self.export_button)

        view.polygon_drawn.connect(self._on_polygon_drawn)
        view.drawing_cancelled.connect(self._show_state)
        fields.fields_changed.connect(self._show_state)
        fields.selection_changed.connect(self._show_state)
        self._show_state()

    # -- slots -------------------------------------------------------------

    def _on_draw_clicked(self, checked):
        if checked:
            self.view.start_polygon_drawing()
        else:
            self.view.cancel_drawing()
        self._show_state()

    def _on_polygon_drawn(self, vertices):
        self._show_state()
        details = self._ask_details(vertices)
        if details is None:
            return                      # Cancel: the drawing is discarded
        name, color, data = details
        try:
            self.fields.add(name, vertices, color, data)
        except (ValueError, OSError) as exc:
            dialogs.inform(self, tr("fields.title"), tr("fields.save_failed", error=exc))

    def _on_export_clicked(self):
        default = str(Path.home() / tr("fields.export_default_file"))
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("fields.export_title"), default, tr("fields.export_filter"))
        if not path:
            return
        if not path.lower().endswith((".geojson", ".json")):
            path += ".geojson"
        try:
            count = self.fields.export(path, self.fields.selected() or None)
        except OSError as exc:
            dialogs.inform(self, tr("fields.export_title"), tr("fields.export_failed", error=exc))
            return
        dialogs.inform(self, tr("fields.export_title"),
                       tr("fields.export_done", count=count, path=path))

    # -- helpers -----------------------------------------------------------

    def _show_state(self):
        drawing = self.view.is_drawing()
        self.draw_button.setChecked(drawing)
        self.draw_button.setText(tr("fields.drawing") if drawing else tr("fields.draw"))
        self.hint_label.setVisible(drawing)
        chosen = len(self.fields.selected())
        self.export_button.setText(tr("fields.export_selected", count=chosen) if chosen
                                   else tr("fields.export_all"))
        self.export_button.setEnabled(self.fields.count() > 0)

    # (list vertices)
    # asks for the details of the field just drawn: (name, color, data), or
    # None when the user cancels
    def _ask_details(self, vertices):
        dialog = FieldDialog(self.fields.store, vertices=vertices, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dialog.name(), dialog.color(), dialog.data()
        return None
