"""Menu shown when the user right-clicks a field on the map: edit, analyze,
zoom to, check / uncheck and delete it, without going to the side panel."""

from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets


# opens the field menu on MapView.layer_right_clicked. window is the
# MainWindow (its panel edits / deletes, its analyze() analyzes)
class FieldMenu:

    # (MainWindow window)
    # listens to right clicks on the window's map
    def __init__(self, window):
        self.window = window
        window.view.layer_right_clicked.connect(self._on_right_click)

    # (str layer_id)
    # the menu for this field; each action runs after the menu has closed
    def build(self, layer_id):
        fields, panel = self.window.fields, self.window.panel
        field = fields.field(layer_id)
        menu = QtWidgets.QMenu(self.window)
        title = menu.addAction(field.name)
        title.setEnabled(False)
        menu.addSeparator()
        checked = fields.is_selected(layer_id)
        actions = (
            ("edit", tr("menu.edit"), lambda: panel.edit_field(layer_id)),
            ("analyze", tr("menu.analyze"), lambda: self.window.analyze(layer_id)),
            ("zoom", tr("menu.zoom"), lambda: fields.zoom_to(layer_id)),
            ("check", tr("menu.uncheck") if checked else tr("menu.check"),
             lambda: fields.set_selected(layer_id, not checked)),
            (None, None, None),
            ("delete", tr("menu.delete"), lambda: panel.delete_field(layer_id)),
        )
        for name, text, slot in actions:
            if name is None:
                menu.addSeparator()
                continue
            action = menu.addAction(text)
            action.setObjectName(name)
            # later: the menu must close before a dialog opens or the list changes
            action.triggered.connect(lambda _=False, s=slot: QtCore.QTimer.singleShot(0, s))
        return menu

    def _on_right_click(self, layer_id, lon, lat):
        if self.window.fields.field(layer_id) is None or self.window.view.is_drawing():
            return
        self.window.hover_card.show_field(None)      # the card would cover the menu
        self.build(layer_id).exec(QtGui.QCursor.pos())
