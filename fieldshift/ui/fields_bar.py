"""Bar under the map: "Draw field" on the left, "Export fields…" on the right.

Uses the map only through MapView and the fields through FieldsManager.
Every text comes from fieldshift/i18n/<language>.json.
"""

from pathlib import Path

from fieldshift.i18n import tr
from fieldshift.qt import QtWidgets
from fieldshift.ui import dialogs

# look of the bar and of its main button
BAR_STYLE = """
QFrame#fieldsBar { background: #f4f6f4; border-top: 1px solid #c9d1c9; }
QPushButton#drawField { background: #2e7d32; color: white; border: none;
                        border-radius: 4px; padding: 6px 16px; font-weight: bold; }
QPushButton#drawField:hover { background: #276b2b; }
QPushButton#drawField:checked { background: #f9a825; color: #222; }
QLabel#drawHint { color: #444; }
"""


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
        name = self._ask_name()
        if not name:
            return                      # Cancel: the drawing is discarded
        try:
            self.fields.add(name, vertices)
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

    def _ask_name(self):
        dialog = FieldNameDialog(self.fields.store, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dialog.name()
        return None
