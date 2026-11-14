"""List of the user's layers: a row per layer with a checkbox and, for
fields, an "Edit" button drawn at the right end of the row."""

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets

# role: the layer id of a row; and True on rows that get an Edit button
LAYER_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
EDITABLE_ROLE = QtCore.Qt.ItemDataRole(int(QtCore.Qt.ItemDataRole.UserRole) + 1)

# space (pixels) between the Edit button and the row edge / the row text
_MARGIN = 4


# (QRect row_rect, QFontMetrics metrics)
# where the Edit button of a row is: right-aligned, slightly smaller than the row
def edit_button_rect(row_rect, metrics):
    width = metrics.horizontalAdvance(tr("common.edit")) + 24
    height = min(row_rect.height() - 2 * 2, metrics.height() + 10)
    top = row_rect.top() + (row_rect.height() - height) // 2
    return QtCore.QRect(row_rect.right() - _MARGIN - width, top, width, height)


# paints the usual row (checkbox and name), then an Edit button on the rows
# marked EDITABLE_ROLE; the name is cut short so it never runs under the button
class _RowDelegate(QtWidgets.QStyledItemDelegate):

    def paint(self, painter, option, index):
        if not index.data(EDITABLE_ROLE):
            super().paint(painter, option, index)
            return
        button_rect = edit_button_rect(option.rect, option.fontMetrics)
        shortened = QtWidgets.QStyleOptionViewItem(option)
        shortened.rect.setRight(button_rect.left() - _MARGIN)
        super().paint(painter, shortened, index)

        button = QtWidgets.QStyleOptionButton()
        button.rect = button_rect
        button.text = tr("common.edit")
        button.state = QtWidgets.QStyle.StateFlag.State_Enabled | QtWidgets.QStyle.StateFlag.State_Raised
        widget = option.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, button, painter, widget)


# QListWidget whose field rows have an Edit button. clicking the button
# emits edit_requested(layer_id) and does nothing else (no zoom, no check)
class FieldList(QtWidgets.QListWidget):

    # emitted with the layer id (str) when an Edit button is clicked
    edit_requested = QtCore.pyqtSignal(str)

    # (QWidget parent = None)
    # creates the list with the Edit-button delegate
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_RowDelegate(self))
        self.setMouseTracking(True)

    # (QPoint pos)
    # the layer id whose Edit button is at viewport position pos, or None
    def edit_button_at(self, pos):
        item = self.itemAt(pos)
        if item is None or not item.data(EDITABLE_ROLE):
            return None
        if edit_button_rect(self.visualItemRect(item), self.fontMetrics()).contains(pos):
            return item.data(LAYER_ID_ROLE)
        return None

    def mouseReleaseEvent(self, event):
        layer_id = self.edit_button_at(event.position().toPoint())
        if layer_id is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            self.edit_requested.emit(layer_id)
            return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        over_button = self.edit_button_at(event.position().toPoint()) is not None
        self.viewport().setCursor(QtGui.QCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if over_button
            else QtCore.Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)
