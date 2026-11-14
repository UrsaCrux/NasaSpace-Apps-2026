"""Dialog to save a new field or edit a saved one: name, colour and zone data."""

from fieldshift.fields.schema import (
    DATA_FIELDS,
    DEFAULT_COLOR,
    KIND_BOOL,
    KIND_CHOICE,
    SOURCE_PREFILLED,
    SOURCE_USER,
    normalize_color,
    normalize_data,
    prefill_data,
)
from fieldshift.i18n import tr
from fieldshift.qt import QtGui, QtWidgets
from fieldshift.ui.dialogs import CenteredDialog


# (str key, any value)
# text of a datum's value in the current language ("Clay", "6.5 ", "Yes"...)
def format_value(spec, value):
    if spec.kind == KIND_CHOICE:
        return tr(f"data_fields.{spec.key}.{value}")
    if spec.kind == KIND_BOOL:
        return tr("common.yes") if value else tr("common.no")
    text = f"{value:.{spec.decimals}f}"
    return f"{text} {spec.unit}" if spec.unit else text


# (str key)
# translated name of a datum ("Soil type")
def data_label(key):
    return tr(f"data_fields.{key}")


# dialog with the details of a field. needs a name (required, unique); the
# colour (grey if never chosen) and the zone data of schema.DATA_FIELDS are
# optional. each datum starts prefilled; changing it marks it "edited" and a
# button brings the prefilled value back. with field= it edits that saved
# field (its own name is not a duplicate), otherwise it asks for a new one
# drawn with vertices=
class FieldDialog(CenteredDialog):

    # (FieldStore store, list vertices = None, Field field = None, QWidget parent = None)
    # builds the dialog; Save stays disabled while the name is not valid
    def __init__(self, store, vertices=None, field=None, parent=None):
        super().__init__(parent)
        self.store = store
        self._own_name = field.name if field is not None else None
        vertices = list(field.vertices) if field is not None else list(vertices)
        self._prefilled = prefill_data(vertices)
        current = normalize_data(field.data if field is not None else None, vertices)
        self._color = normalize_color(field.color if field is not None else DEFAULT_COLOR)
        self.setWindowTitle(tr("fields.edit_title") if field is not None
                            else tr("fields.save_title"))
        self.setMinimumWidth(460)

        name = field.name if field is not None else store.suggest_name(tr("fields.default_name"))
        self.name_edit = QtWidgets.QLineEdit(name)
        self.name_edit.selectAll()
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #b00020;")
        self.error_label.setWordWrap(True)

        self.color_button = QtWidgets.QPushButton(tr("fields.color_choose"))
        self.color_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                        QtWidgets.QSizePolicy.Policy.Fixed)
        self.color_button.setMinimumWidth(140)
        self.color_button.clicked.connect(self._choose_color)
        self._show_color()

        top = QtWidgets.QFormLayout()
        # macOS keeps form fields at their natural (short) width by default
        top.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        top.addRow(tr("fields.name_label"), self.name_edit)
        top.addRow(self.error_label)
        top.addRow(tr("fields.color_label"), self.color_button)

        self._rows = {}
        data_box = QtWidgets.QGroupBox(tr("fields.data_title"))
        data_layout = QtWidgets.QGridLayout(data_box)
        hint = QtWidgets.QLabel(tr("fields.data_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        data_layout.addWidget(hint, 0, 0, 1, 4)
        for row, spec in enumerate(DATA_FIELDS, start=1):
            self._add_data_row(data_layout, row, spec, current[spec.key])

        Buttons = QtWidgets.QDialogButtonBox.StandardButton
        buttons = QtWidgets.QDialogButtonBox(Buttons.Save | Buttons.Cancel)
        self.save_button = buttons.button(Buttons.Save)
        self.save_button.setText(tr("common.save"))
        buttons.button(Buttons.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(data_box)
        layout.addWidget(buttons)

        self.name_edit.textChanged.connect(self._validate)
        self._validate()

    # ()
    # the name typed, without surrounding spaces
    def name(self):
        return self.name_edit.text().strip()

    # ()
    # the chosen colour as "#rrggbb" (grey when none was chosen)
    def color(self):
        return self._color

    # ()
    # the data as schema.DATA_FIELDS describes it: {key: {"value", "source"}}
    def data(self):
        return {key: {"value": self._value(row),
                      "source": SOURCE_USER if row["modified"] else SOURCE_PREFILLED}
                for key, row in self._rows.items()}

    # (str key)
    # True when the user changed this datum (it is not the prefilled one)
    def is_modified(self, key):
        return self._rows[key]["modified"]

    # (str key, any value)
    # sets a datum as if the user had typed it (marks it edited)
    def set_value(self, key, value):
        row = self._rows[key]
        self._write(row, value)
        self._mark(row, True)

    # (str key)
    # puts the prefilled value back and marks the datum as not edited
    def reset_value(self, key):
        row = self._rows[key]
        self._write(row, self._prefilled[key]["value"])
        self._mark(row, False)

    # -- colour ------------------------------------------------------------

    def _choose_color(self):
        picked = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._color), self, tr("fields.color_choose_title"))
        if picked.isValid():
            self._color = normalize_color(picked.name())
            self._show_color()

    def _show_color(self):
        dark = QtGui.QColor(self._color).lightness() < 140
        self.color_button.setStyleSheet(
            f"QPushButton {{ background: {self._color}; color: {'white' if dark else 'black'};"
            " border: 1px solid #777; border-radius: 4px; padding: 5px 14px; }")

    # -- data rows ---------------------------------------------------------

    def _add_data_row(self, grid, row, spec, item):
        editor = self._make_editor(spec)
        status = QtWidgets.QLabel()
        reset = QtWidgets.QToolButton()
        reset.setText("↺")
        reset.setToolTip(tr("fields.data_reset"))
        parts = {"spec": spec, "editor": editor, "status": status, "reset": reset,
                 "modified": False, "loading": True}
        self._rows[spec.key] = parts
        self._write(parts, item["value"])
        parts["loading"] = False
        self._mark(parts, item["source"] == SOURCE_USER)

        reset.clicked.connect(lambda: self.reset_value(spec.key))
        signal = editor.valueChanged if hasattr(editor, "valueChanged") else editor.activated
        signal.connect(lambda *_: self._on_user_edit(spec.key))
        grid.addWidget(QtWidgets.QLabel(data_label(spec.key)), row, 0)
        grid.addWidget(editor, row, 1)
        grid.addWidget(status, row, 2)
        grid.addWidget(reset, row, 3)
        grid.setColumnStretch(1, 1)

    def _make_editor(self, spec):
        editor = self._new_editor(spec)
        editor.setMinimumWidth(170)        # every datum gets the same width
        editor.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                             QtWidgets.QSizePolicy.Policy.Fixed)
        return editor

    def _new_editor(self, spec):
        if spec.kind == KIND_CHOICE:
            box = QtWidgets.QComboBox()
            for option in spec.options:
                box.addItem(tr(f"data_fields.{spec.key}.{option}"), option)
            return box
        if spec.kind == KIND_BOOL:
            box = QtWidgets.QComboBox()
            box.addItem(tr("common.yes"), True)
            box.addItem(tr("common.no"), False)
            return box
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(spec.minimum, spec.maximum)
        spin.setDecimals(spec.decimals)
        if spec.unit:
            spin.setSuffix(f" {spec.unit}")
        return spin

    # writes a value into the editor without counting it as a user edit
    def _write(self, row, value):
        editor = row["editor"]
        row["loading"] = True
        try:
            if hasattr(editor, "setValue"):
                editor.setValue(float(value))
            else:
                editor.setCurrentIndex(editor.findData(value))
        finally:
            row["loading"] = False

    def _value(self, row):
        editor = row["editor"]
        if hasattr(editor, "value"):
            return round(editor.value(), row["spec"].decimals)
        return editor.currentData()

    def _on_user_edit(self, key):
        row = self._rows[key]
        if not row["loading"]:
            self._mark(row, True)

    def _mark(self, row, modified):
        row["modified"] = modified
        row["status"].setText(tr("fields.data_edited") if modified else tr("fields.data_prefilled"))
        row["status"].setStyleSheet("color: #1b5e20; font-weight: bold;" if modified
                                    else "color: #777; font-style: italic;")
        row["reset"].setVisible(modified)

    def _validate(self):
        problem = self.store.name_problem(self.name_edit.text(), ignore=self._own_name)
        messages = {"empty": tr("fields.error_empty"),
                    "duplicate": tr("fields.error_duplicate", name=self.name())}
        self.error_label.setText(messages.get(problem, ""))
        self.error_label.setVisible(problem is not None)     # no empty gap
        self.save_button.setEnabled(problem is None)
