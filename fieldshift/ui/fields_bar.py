"""Bar under the map: "My fields" / "Status" / "Trends" (what the right
column shows) and "Analyze…" on the left, "Export fields…" on the right. The
"Draw field" button floats over the bottom-right corner of the map.

Uses the map only through MapView and the fields through FieldsManager.
Every text comes from fieldshift/i18n/<language>.json.
"""

from pathlib import Path

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui import dialogs
from fieldshift.ui.field_dialog import FieldDialog

# look of the bar and of its main button
BAR_STYLE = """
QFrame#fieldsBar { background: #f4f6f4; border-top: 1px solid #c9d1c9; }
QPushButton#myFields, QPushButton#statusMode { background: white; color: #2e3b2e;
    border: 1px solid #9aa39a; padding: 6px 16px; font-weight: bold; }
QPushButton#myFields { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }
QPushButton#statusMode { border-left: none; }
QPushButton#trendsMode { background: white; color: #2e3b2e; border: 1px solid #9aa39a;
    border-left: none; padding: 6px 16px; font-weight: bold;
    border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QPushButton#myFields:hover, QPushButton#statusMode:hover,
QPushButton#trendsMode:hover { background: #e8f5e9; }
QPushButton#trendsMode:checked { background: #6a1b9a; color: white; border-color: #6a1b9a; }
QPushButton#trendsMode:disabled { background: #eceff1; color: #b0bec5; }
QPushButton#myFields:checked { background: #2e7d32; color: white; border-color: #2e7d32; }
QPushButton#statusMode:checked { background: #00796b; color: white; border-color: #00796b; }
QPushButton#statusMode:disabled { background: #eceff1; color: #b0bec5; }
QPushButton#analyzeFields { background: #1565c0; color: white; border: none;
                            border-radius: 4px; padding: 6px 16px; font-weight: bold; }
QPushButton#analyzeFields:hover { background: #0d47a1; }
QPushButton#analyzeFields:disabled { background: #b0bec5; color: #eceff1; }
QLabel#drawHint { color: #444; }
"""

# the floating "Draw field" button
DRAW_STYLE = """
QPushButton#drawField { background: #2e7d32; color: white; border: 1px solid #1b5e20;
                        border-radius: 18px; padding: 8px 18px; font-weight: bold; }
QPushButton#drawField:hover { background: #276b2b; }
QPushButton#drawField:checked { background: #f9a825; color: #222; border-color: #c17900; }
"""
# distance (pixels) of the "Draw field" button from the bottom-right corner
DRAW_MARGIN_PX = 14


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

        # over the bottom-right corner of the map
        self.draw_button = QtWidgets.QPushButton(tr("fields.draw"), view.widget())
        self.draw_button.setObjectName("drawField")
        self.draw_button.setStyleSheet(DRAW_STYLE)
        self.draw_button.setCheckable(True)
        self.draw_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.draw_button.clicked.connect(self._on_draw_clicked)
        view.widget().installEventFilter(self)
        # what the right column shows: "My fields", "Status" or "Trends"
        self.mode = "fields"
        # emitted with no arguments when the user clicks "My fields"
        self.fields_requested = Event()
        self.fields_button = QtWidgets.QPushButton(tr("modes.fields"))
        self.fields_button.setObjectName("myFields")
        self.fields_button.setCheckable(True)
        self.fields_button.setChecked(True)
        self.fields_button.clicked.connect(lambda: self.fields_requested.emit())
        self.hint_label = QtWidgets.QLabel(tr("fields.hint"))
        self.hint_label.setObjectName("drawHint")
        self.hint_label.setWordWrap(True)
        # emitted with no arguments when the user clicks "Analyze…"
        self.analyze_requested = Event()
        self.analyze_button = QtWidgets.QPushButton(tr("analysis.button"))
        self.analyze_button.setObjectName("analyzeFields")
        self.analyze_button.clicked.connect(lambda: self.analyze_requested.emit())
        # emitted with no arguments when the user clicks "Status" / "Trends"
        self.status_requested = Event()
        self.trends_requested = Event()
        self.status_button = QtWidgets.QPushButton(tr("modes.status"))
        self.status_button.setObjectName("statusMode")
        self.status_button.setCheckable(True)
        self.status_button.clicked.connect(lambda: self.status_requested.emit())
        self.trends_button = QtWidgets.QPushButton(tr("modes.trends"))
        self.trends_button.setObjectName("trendsMode")
        self.trends_button.setCheckable(True)
        self.trends_button.clicked.connect(lambda: self.trends_requested.emit())
        self.export_button = QtWidgets.QPushButton(tr("fields.export_all"))
        self.export_button.clicked.connect(lambda: self._on_export_clicked())

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.addWidget(self.fields_button)
        row.addWidget(self.status_button)
        row.addWidget(self.trends_button)
        row.addSpacing(8)
        row.addWidget(self.analyze_button)
        row.addWidget(self.hint_label, 1)
        row.addStretch(0)
        row.addWidget(self.export_button)

        view.polygon_drawn.connect(self._on_polygon_drawn)
        view.drawing_cancelled.connect(self._show_state)
        fields.fields_changed.connect(self._show_state)
        fields.selection_changed.connect(self._show_state)
        self._show_state()

    # (str mode)
    # marks "My fields" ("fields"), "Status" ("status") or "Trends"
    # ("trends") as the one shown
    def set_mode(self, mode):
        self.mode = mode
        self.fields_button.setChecked(mode == "fields")
        self.status_button.setChecked(mode == "status")
        self.trends_button.setChecked(mode == "trends")

    def eventFilter(self, watched, event):
        view = getattr(self, "view", None)       # None while Qt tears the bar down
        if (view is not None and event.type() == QtCore.QEvent.Type.Resize
                and watched is view.widget()):
            self._place_draw_button()
        return False

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
        self._place_draw_button()
        self.hint_label.setVisible(drawing)
        chosen = len(self.fields.selected())
        self.export_button.setText(tr("fields.export_selected", count=chosen) if chosen
                                   else tr("fields.export_all"))
        self.export_button.setEnabled(self.fields.count() > 0)
        can_analyze = self.fields.count() > 0 and not drawing
        tip = "" if self.fields.count() else tr("analysis.button_tooltip")
        for button in (self.status_button, self.trends_button, self.analyze_button):
            button.setEnabled(can_analyze)
            button.setToolTip(tip)
        self.set_mode(self.mode)

    def _place_draw_button(self):
        button, parent = self.draw_button, self.view.widget()
        button.adjustSize()
        button.move(max(0, parent.width() - button.width() - DRAW_MARGIN_PX),
                    max(0, parent.height() - button.height() - DRAW_MARGIN_PX))
        button.raise_()

    # (list vertices)
    # asks for the details of the field just drawn: (name, color, data), or
    # None when the user cancels
    def _ask_details(self, vertices):
        dialog = FieldDialog(self.fields.store, vertices=vertices, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            return dialog.name(), dialog.color(), dialog.data()
        return None
