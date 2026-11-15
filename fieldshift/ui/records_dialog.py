"""Window with the measurements and events of one field (fields.records):
a list (date and time, what, value, how it was recorded, note) and a form to
add one, measured now or at another moment. Values typed in "Edit field"
show here too (as "edited"): both write the same records.
"""

from fieldshift.fields.records import KINDS, Record
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui import dialogs
from fieldshift.ui.dialogs import CenteredDialog


# the records window of a field
class RecordsDialog(CenteredDialog):

    # (FieldsManager fields, str layer_id, QWidget parent = None)
    def __init__(self, fields, layer_id, parent=None):
        super().__init__(parent)
        self.fields = fields
        self.layer_id = layer_id
        field = fields.field(layer_id)
        self.setWindowTitle(tr("records.title", field=field.name))
        self.resize(640, 520)

        intro = QtWidgets.QLabel(tr("records.intro"))
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #555;")

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr(f"records.col.{c}") for c in
                                              ("time", "kind", "value", "origin", "note")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.delete_button = QtWidgets.QPushButton(tr("records.delete"))
        self.delete_button.clicked.connect(self.delete_selected)

        # the form of a new record
        self.kind_box = QtWidgets.QComboBox()
        for kind in KINDS:
            self.kind_box.addItem(tr(f"records.kind.{kind}"), kind)
        self.kind_box.currentIndexChanged.connect(self._on_kind)
        self.value_box = QtWidgets.QDoubleSpinBox()
        self.value_box.setRange(-1_000_000, 1_000_000)
        self.time_box = QtWidgets.QDateTimeEdit(QtCore.QDateTime.currentDateTime())
        self.time_box.setCalendarPopup(True)
        self.time_box.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.note_box = QtWidgets.QLineEdit()
        self.note_box.setPlaceholderText(tr("records.note_placeholder"))
        self.add_button = QtWidgets.QPushButton(tr("records.add"))
        self.add_button.clicked.connect(self.add_from_form)
        form = QtWidgets.QFormLayout()
        form.addRow(tr("records.col.kind"), self.kind_box)
        form.addRow(tr("records.col.value"), self.value_box)
        form.addRow(tr("records.col.time"), self.time_box)
        form.addRow(tr("records.col.note"), self.note_box)
        box = QtWidgets.QGroupBox(tr("records.new"))
        box_layout = QtWidgets.QVBoxLayout(box)
        box_layout.addLayout(form)
        box_layout.addWidget(self.add_button, 0, QtCore.Qt.AlignmentFlag.AlignRight)

        close = QtWidgets.QDialogButtonBox()
        close.addButton(tr("records.close"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        close.accepted.connect(self.accept)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.delete_button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(box)
        layout.addWidget(close)
        self._on_kind()
        self.fill()

    # ()
    # shows the field's records, newest first
    def fill(self):
        self.records = list(reversed(self.fields.records(self.layer_id)))
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            unit, decimals = KINDS[record.kind][0], KINDS[record.kind][1]
            value = "—" if record.value is None else f"{record.value:.{decimals}f} {unit}".strip()
            cells = (record.time.replace("T", " "), tr(f"records.kind.{record.kind}"), value,
                     tr(f"records.origin.{record.origin}"), record.note)
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        self.delete_button.setEnabled(bool(self.records))

    # ()
    # adds the record of the form; returns it
    def add_from_form(self):
        kind = self.kind_box.currentData()
        has_value = KINDS[kind][3]
        record = Record(self.time_box.dateTime().toString("yyyy-MM-ddTHH:mm"), kind,
                        self.value_box.value() if has_value else None,
                        self.note_box.text().strip())
        self.fields.add_record(self.layer_id, record)
        self.note_box.clear()
        self.fill()
        return record

    # ()
    # deletes the selected records, after asking
    def delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        if not dialogs.confirm(self, tr("records.delete"), tr("records.delete_confirm",
                                                              count=len(rows)),
                               tr("records.delete"), danger=True):
            return
        for row in rows:
            self.fields.remove_record(self.layer_id, self.records[row])
        self.fill()

    def _on_kind(self):
        kind = self.kind_box.currentData()
        unit, decimals, _, has_value = KINDS[kind]
        self.value_box.setEnabled(has_value)
        self.value_box.setDecimals(decimals)
        self.value_box.setSuffix(f" {unit}" if unit else "")
