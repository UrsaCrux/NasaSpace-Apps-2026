"""Side panel box with the data of the fields the user checked.

For now: name, area and creation date of each field, plus the total area.
Later each field will get its own sheet with tabs (climate, risk, rotation).
"""

from datetime import datetime

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets


# (str iso_text)
# creation date in local time ("2026-11-14 09:30"); the raw text if unreadable
def format_created(iso_text):
    try:
        return datetime.fromisoformat(iso_text).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso_text


# box listing the checked fields in a small table, with the total area
class FieldsDataBox(QtWidgets.QGroupBox):

    # (FieldsManager fields, QWidget parent = None)
    # builds the box and follows the checked fields
    def __init__(self, fields, parent=None):
        super().__init__(tr("data.title"), parent)
        self.fields = fields

        self.empty_label = QtWidgets.QLabel(tr("data.empty"))
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #666;")

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [tr("data.col_name"), tr("data.col_area"), tr("data.col_created")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.setMaximumHeight(170)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.total_label = QtWidgets.QLabel()
        self.total_label.setStyleSheet("font-weight: bold;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.table)
        layout.addWidget(self.total_label)

        fields.selection_changed.connect(self.refresh)
        fields.fields_changed.connect(self.refresh)
        self.refresh()

    # ()
    # fills the table with the fields checked right now
    def refresh(self):
        chosen = [self.fields.field(i) for i in self.fields.selected()]
        self.table.setRowCount(len(chosen))
        right = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        for row, field in enumerate(chosen):
            area = QtWidgets.QTableWidgetItem(f"{field.area_ha:.2f}")
            area.setTextAlignment(right)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(field.name))
            self.table.setItem(row, 1, area)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(format_created(field.created)))
        total = sum(f.area_ha for f in chosen)
        self.total_label.setText(tr("data.total", count=len(chosen), area=f"{total:.2f}"))
        self.empty_label.setVisible(not chosen)
        self.table.setVisible(bool(chosen))
        self.total_label.setVisible(bool(chosen))
