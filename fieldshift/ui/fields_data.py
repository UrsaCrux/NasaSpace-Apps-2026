"""Side panel box with the data of the fields the user checked.

Each checked field is a tree node (colour swatch, name, area) with its
creation date and its zone data below. Later each field will get its own
sheet with tabs (climate, risk, rotation).
"""

from datetime import datetime

from fieldshift import crops
from fieldshift.fields.schema import CROP_KEY, DATA_FIELDS, SOURCE_MISSING, SOURCE_USER
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.ui.field_dialog import data_label, format_value


# (str iso_text)
# creation date in local time ("2026-11-14"); the raw text if unreadable
def format_created(iso_text):
    try:
        return datetime.fromisoformat(iso_text).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return iso_text


# (str color)
# small square icon filled with a "#rrggbb" colour
def color_icon(color):
    pixmap = QtGui.QPixmap(14, 14)
    pixmap.fill(QtGui.QColor(color))
    return QtGui.QIcon(pixmap)


# box listing the checked fields as a tree, with the total area
class FieldsDataBox(QtWidgets.QGroupBox):

    # (FieldsManager fields, QWidget parent = None)
    # builds the box and follows the checked fields
    def __init__(self, fields, parent=None):
        super().__init__(tr("data.title"), parent)
        self.fields = fields

        self.empty_label = QtWidgets.QLabel(tr("data.empty"))
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("color: #666;")

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setMinimumHeight(150)
        self.tree.setMaximumHeight(300)
        header = self.tree.header()
        header.setStretchLastSection(False)
        # label column fits its text; the value column takes the rest
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)

        self.total_label = QtWidgets.QLabel()
        self.total_label.setStyleSheet("font-weight: bold;")
        self.legend_label = QtWidgets.QLabel(tr("data.legend"))
        self.legend_label.setWordWrap(True)
        self.legend_label.setStyleSheet("color: #666; font-size: 11px;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.tree)
        layout.addWidget(self.total_label)
        layout.addWidget(self.legend_label)

        fields.selection_changed.connect(self.refresh)
        fields.fields_changed.connect(self.refresh)
        self.refresh()

    # ()
    # number of fields shown
    def field_count(self):
        return self.tree.topLevelItemCount()

    # ()
    # rebuilds the tree from the fields checked right now
    def refresh(self):
        chosen = [self.fields.field(i) for i in self.fields.selected()]
        self.tree.clear()
        bold = self.tree.font()
        bold.setBold(True)
        right = QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        for field in chosen:
            node = QtWidgets.QTreeWidgetItem(
                [field.name, tr("data.area", area=f"{field.area_ha:.2f}")])
            node.setIcon(0, color_icon(field.color))
            node.setFont(0, bold)
            node.setTextAlignment(1, right)
            self.tree.addTopLevelItem(node)
            created = QtWidgets.QTreeWidgetItem(
                [tr("data.col_created"), format_created(field.created)])
            created.setTextAlignment(1, right)
            node.addChild(created)
            crop_item = field.data.get(CROP_KEY, {})
            crop_id = crop_item.get("value")
            crop_text = (crop_item.get("name") or crops.label(crop_id)) if crop_id \
                else tr("data.no_crop")
            crop = QtWidgets.QTreeWidgetItem([tr("data.crop"), crop_text])
            crop.setTextAlignment(1, right)
            crop.setFont(1, bold)
            node.addChild(crop)
            for spec in DATA_FIELDS:
                item = field.data[spec.key]
                edited = item["source"] == SOURCE_USER
                missing = item["source"] == SOURCE_MISSING
                row = QtWidgets.QTreeWidgetItem([data_label(spec.key), format_value(spec, item["value"])])
                # edited by the agronomist: bold green; preloaded: grey; missing: orange
                source = (tr("fields.data_missing") if missing else
                          tr("fields.data_edited") if edited else tr("fields.data_prefilled"))
                row.setToolTip(1, source)
                row.setToolTip(0, source)
                color = "#c06000" if missing else "#1b5e20" if edited else "#666666"
                row.setForeground(1, QtGui.QBrush(QtGui.QColor(color)))
                if edited:
                    row.setFont(1, bold)
                row.setTextAlignment(1, right)
                node.addChild(row)
            node.setExpanded(True)
        total = sum(f.area_ha for f in chosen)
        self.total_label.setText(tr("data.total", count=len(chosen), area=f"{total:.2f}"))
        self.empty_label.setVisible(not chosen)
        self.tree.setVisible(bool(chosen))
        self.total_label.setVisible(bool(chosen))
        self.legend_label.setVisible(bool(chosen))
