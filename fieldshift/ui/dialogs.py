"""Small dialogs drawn by Qt itself.

QMessageBox may use the native macOS alert, which shows the Python/app icon
(it looks like a folder or file) and can confuse users. These dialogs only
show text and buttons.
"""

from fieldshift.i18n import tr
from fieldshift.qt import QtWidgets

# style of the button that deletes something
DANGER_STYLE = ("QPushButton { background: #c62828; color: white; border: none;"
                " border-radius: 4px; padding: 5px 14px; }"
                "QPushButton:hover { background: #b71c1c; }")


# (QWidget parent, str title, str text, str confirm_text, bool danger = False)
# asks a yes/no question; returns True when the user clicks confirm_text
def confirm(parent, title, text, confirm_text, danger=False):
    dialog, buttons = _base(parent, title, text)
    cancel = buttons.addButton(tr("common.cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
    ok = buttons.addButton(confirm_text, QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
    if danger:
        ok.setStyleSheet(DANGER_STYLE)
        cancel.setDefault(True)          # Enter does not delete by accident
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


# (QWidget parent, str title, str text)
# shows a message with an OK button
def inform(parent, title, text):
    dialog, buttons = _base(parent, title, text)
    buttons.addButton(tr("common.ok"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
    dialog.exec()


def _base(parent, title, text):
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(340)
    label = QtWidgets.QLabel(text)
    label.setWordWrap(True)
    buttons = QtWidgets.QDialogButtonBox()
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(label)
    layout.addSpacing(8)
    layout.addWidget(buttons)
    return dialog, buttons
