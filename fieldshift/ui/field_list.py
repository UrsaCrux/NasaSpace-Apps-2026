"""List of the user's layers: a row per layer with a checkbox and, for
fields, an "Edit" button drawn at the right end of the row."""

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets

# role: the layer id of a row; and True on rows that get an Edit button
LAYER_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
EDITABLE_ROLE = QtCore.Qt.ItemDataRole(int(QtCore.Qt.ItemDataRole.UserRole) + 1)

# space (pixels) between the Edit button and the row edge / the row text
_MARGIN = 6
# minimum height (pixels) of a row, so the Edit button fits comfortably
ROW_HEIGHT = 30

# look of the Edit button (drawn by hand: the native macOS button has a fixed
# height and comes out cut in a list row)
_BUTTON_FILL = QtGui.QColor("#ffffff")
_BUTTON_HOVER = QtGui.QColor("#e8f1e8")
_BUTTON_BORDER = QtGui.QColor("#b0b7b0")
_BUTTON_TEXT = QtGui.QColor("#1f2a1f")


# (QRect row_rect, QFontMetrics metrics)
# where the Edit button of a row is: right-aligned and vertically centred
def edit_button_rect(row_rect, metrics):
    width = metrics.horizontalAdvance(tr("common.edit")) + 22
    height = min(row_rect.height() - 6, metrics.height() + 8)
    top = row_rect.top() + (row_rect.height() - height) // 2
    return QtCore.QRect(row_rect.right() - _MARGIN - width, top, width, height)


# paints the usual row (checkbox and name), then an Edit button on the rows
# marked EDITABLE_ROLE; the name is cut short so it never runs under the button
class _RowDelegate(QtWidgets.QStyledItemDelegate):

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QtCore.QSize(size.width(), max(size.height(), ROW_HEIGHT))

    def paint(self, painter, option, index):
        if not index.data(EDITABLE_ROLE):
            super().paint(painter, option, index)
            return
        button_rect = edit_button_rect(option.rect, option.fontMetrics)
        shortened = QtWidgets.QStyleOptionViewItem(option)
        shortened.rect.setRight(button_rect.left() - _MARGIN)
        super().paint(painter, shortened, index)

        widget = option.widget
        hovered = widget is not None and widget.hovered_edit == index.data(LAYER_ID_ROLE)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(_BUTTON_BORDER, 1))
        painter.setBrush(_BUTTON_HOVER if hovered else _BUTTON_FILL)
        painter.drawRoundedRect(QtCore.QRectF(button_rect).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
        painter.setPen(_BUTTON_TEXT)
        painter.setFont(option.font)
        painter.drawText(button_rect, QtCore.Qt.AlignmentFlag.AlignCenter, tr("common.edit"))
        painter.restore()


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
        # layer id of the Edit button under the mouse (drawn highlighted)
        self.hovered_edit = None

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
        hovered = self.edit_button_at(event.position().toPoint())
        if hovered != self.hovered_edit:
            self.hovered_edit = hovered
            self.viewport().update()
        self.viewport().setCursor(QtGui.QCursor(
            QtCore.Qt.CursorShape.PointingHandCursor if hovered is not None
            else QtCore.Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_edit is not None:
            self.hovered_edit = None
            self.viewport().update()
        super().leaveEvent(event)
