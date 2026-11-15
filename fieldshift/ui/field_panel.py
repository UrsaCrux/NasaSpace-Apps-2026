"""Base of the panels that show one field in the right column of the map tab
(Status, Trends): a header with the field chooser, an info line, and a
scrolling content built from a report that loads in a background thread.

Clicking another field on the map shows that field; choosing one in the
list also moves the map to it. Uses the map only through MapView (clicked,
layer_hovered) and the fields through FieldsManager.
"""

import os
import threading

from fieldshift.i18n import tr
from fieldshift.map import Event
from fieldshift.qt import QtCore, QtWidgets

# smallest width of the panel (pixels)
MIN_WIDTH_PX = 480
# when set to "1" reports are built at once in the UI thread (offline: they
# fail at once, or are example numbers in the tests)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"


# (DataError error)
# the user's text for a failed download: "NASA POWER: no internet connection"
def error_text(error):
    from fieldshift.api.errors import DataError, classify
    if not isinstance(error, DataError):
        error = classify(error)
    reason = tr(f"errors.{error.kind}", detail=error.detail)
    return tr("errors.with_source", source=error.source, reason=reason) if error.source \
        else reason


# a box that says why data is missing, with a "Try again" button
class ErrorBox(QtWidgets.QFrame):

    # (str text, callable retry, bool compact = False)
    def __init__(self, text, retry, compact=False, parent=None):
        super().__init__(parent)
        self.setObjectName("errorBox")
        self.setStyleSheet("QFrame#errorBox { background: #fdecea; border: 1px solid #f5c2bd;"
                           " border-radius: 6px; } QLabel { border: none; background:"
                           " transparent; color: #8a1c13; }")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 6 if compact else 10, 10, 6 if compact else 10)
        self.label = QtWidgets.QLabel(text)
        self.label.setWordWrap(True)
        self.retry_button = QtWidgets.QPushButton(tr("errors.retry"))
        self.retry_button.clicked.connect(retry)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.retry_button)

_STYLE = """
QFrame#fieldPanel { background: #f4f6f4; }
QScrollArea, QWidget#panelContent { background: transparent; border: none; }
QPushButton#period { border: 1px solid #9aa39a; padding: 3px 10px; background: white; }
QPushButton#period:checked { background: #00796b; color: white; border-color: #00796b; }
"""


# the panel. subclasses set title_key and implement make_report(field) (any
# thread) and build(report) (UI thread, fills content_layout)
class FieldPanel(QtWidgets.QFrame):

    title_key = ""
    # i18n key of the "loading" text, filled with {field}
    loading_key = "panel.loading"

    # internal: (int request number, report), from the loader thread
    _loaded = QtCore.pyqtSignal(int, object)

    # (MapView view, FieldsManager fields, QWidget parent = None)
    def __init__(self, view, fields, parent=None):
        super().__init__(parent)
        self.view = view
        self.fields = fields
        self.layer_id = None           # field shown
        self.report = None             # report shown (None while loading or failed)
        self.error_box = None          # ErrorBox shown, if any
        self._request = 0
        self._hovered = None           # field under the mouse on the map
        # emitted with (str layer_id) when a "See suggestion" link is clicked
        self.suggestion_requested = Event()
        self.setObjectName("fieldPanel")
        self.setStyleSheet(_STYLE)

        title = QtWidgets.QLabel(f"<b>{tr(self.title_key)}</b>")
        title.setStyleSheet("font-size: 17px;")
        self.field_box = QtWidgets.QComboBox()
        self.field_box.setMinimumWidth(160)
        self.field_box.setToolTip(tr("status.field_tooltip"))
        self.field_box.activated.connect(self._on_field_chosen)
        self.header = QtWidgets.QHBoxLayout()
        self.header.addWidget(title)
        self.header.addSpacing(8)
        self.header.addWidget(self.field_box, 1)

        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("color: #666; font-size: 11px;")
        self.info_label.setWordWrap(True)

        self.content = QtWidgets.QWidget()
        self.content.setObjectName("panelContent")
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 4, 0)
        self.content_layout.setSpacing(10)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.content)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 8, 10)
        layout.setSpacing(6)
        layout.addLayout(self.header)
        layout.addWidget(self.info_label)
        layout.addWidget(self.scroll, 1)
        self.setMinimumWidth(MIN_WIDTH_PX)

        self._loaded.connect(self._on_loaded)
        view.layer_hovered.connect(self._on_hover)
        view.clicked.connect(self._on_map_click)
        fields.fields_changed.connect(self._on_fields_changed)

    # (str layer_id)
    # shows that field (the first one when None). returns True when a field
    # is shown (its report may still be loading)
    def open(self, layer_id=None):
        ids = self.fields.layer_ids()
        if not ids:
            return False
        if layer_id not in ids:
            layer_id = self.layer_id if self.layer_id in ids else ids[0]
        self.layer_id = layer_id
        self._fill_fields()
        self.refresh()
        return True

    # ()
    # loads the report of the field shown again
    def refresh(self):
        field = self.fields.field(self.layer_id)
        if field is None:
            return
        self._request += 1
        self.report = None
        self._clear()
        self.info_label.setText("")
        if os.environ.get(OFFLINE_ENV) == "1":
            try:
                report = self.make_report(field)
            except Exception as exc:
                report = exc
            self._on_loaded(self._request, report)
            return
        waiting = QtWidgets.QLabel(tr(self.loading_key, field=field.name))
        waiting.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        waiting.setWordWrap(True)
        waiting.setStyleSheet("color: #555; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(waiting)
        self.content_layout.addStretch(1)
        threading.Thread(target=self._run, args=(self._request, field), daemon=True,
                         name="field-panel").start()

    # (Field field)
    # the report of the field (runs in a background thread)
    def make_report(self, field):
        raise NotImplementedError

    # (report)
    # fills content_layout with the report (UI thread)
    def build(self, report):
        raise NotImplementedError

    # -- helpers -----------------------------------------------------------

    def _run(self, request, field):
        try:
            report = self.make_report(field)
        except Exception as exc:
            report = exc                        # shown as an error with "Try again"
        self._loaded.emit(request, report)

    def _on_loaded(self, request, report):
        if request != self._request:
            return                              # another field was chosen meanwhile
        self._clear()
        if isinstance(report, Exception):
            # nothing to show: say why, never made-up numbers
            self.report = None
            self.error_box = ErrorBox(error_text(report), self.refresh)
            self.content_layout.addWidget(self.error_box)
            self.content_layout.addStretch(1)
            return
        self.report = report
        self.error_box = None
        missing = getattr(report, "missing", ())
        if missing:
            # some sources did not answer: say which and why, above the rest
            text = tr("errors.partial") + "<br>" + "<br>".join(error_text(e) for e in missing)
            self.error_box = ErrorBox(text, self.refresh, compact=True)
            self.content_layout.addWidget(self.error_box)
        self.build(report)

    def _clear(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _fill_fields(self):
        self.field_box.blockSignals(True)
        self.field_box.clear()
        for layer_id in self.fields.layer_ids():
            self.field_box.addItem(self.fields.field(layer_id).name, layer_id)
        self.field_box.setCurrentIndex(max(0, self.field_box.findData(self.layer_id)))
        self.field_box.blockSignals(False)

    def _on_field_chosen(self, index):
        layer_id = self.field_box.itemData(index)
        self.open(layer_id)
        self.fields.zoom_to(layer_id)

    def _on_hover(self, layer_id, lon, lat):
        self._hovered = layer_id if self.fields.is_field(layer_id) else None

    def _on_map_click(self, lon, lat):
        if self.isVisible() and self._hovered and self._hovered != self.layer_id:
            self.open(self._hovered)

    def _on_fields_changed(self):
        if self.layer_id is None:
            return
        if self.fields.is_field(self.layer_id):
            self._fill_fields()
        elif self.isVisible():
            self.open(None)            # the field shown was deleted
