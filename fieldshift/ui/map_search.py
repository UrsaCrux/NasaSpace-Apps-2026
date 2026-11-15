"""Place search over the map: a panel next to the magnifier button with a
text box and a list of results. Enter searches (the service does not allow
searching while typing), a click on a result takes the map there and drops a
temporary pin.

Uses the map only through MapView (zoom_to_extent, show_pin, clear_pin).
"""

import os
import threading

from fieldshift.api import geocode
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets

# when set to "1" the search never contacts the service (tests)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"
# a found place is never zoomed closer than this half-width (degrees, ~150 m)
MIN_HALF_SPAN_DEG = 0.0015
# distance (pixels) between the controls column and the panel
GAP_PX = 8
# width (pixels) of the panel, and tallest the result list may be
WIDTH_PX = 340
MAX_LIST_HEIGHT_PX = 300

_STYLE = ("QFrame#mapSearch { background: rgba(255, 255, 255, 240); border: 1px solid #9aa39a;"
          " border-radius: 8px; } QLabel { background: transparent; border: none; }"
          "QListWidget { border: none; background: transparent; }"
          "QListWidget::item { padding: 5px 4px; }"
          "QListWidget::item:hover, QListWidget::item:selected { background: #e8f1e8; color: #1b1b1b; }")


# (list bbox)
# (xmin, ymin, xmax, ymax) grown to at least 2 * MIN_HALF_SPAN_DEG on each side,
# so a house is shown with its surroundings
def padded_bbox(bbox):
    xmin, ymin, xmax, ymax = bbox
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    half_x = max((xmax - xmin) / 2 * 1.1, MIN_HALF_SPAN_DEG)
    half_y = max((ymax - ymin) / 2 * 1.1, MIN_HALF_SPAN_DEG)
    return cx - half_x, cy - half_y, cx + half_x, cy + half_y


# the search panel. controls is the MapControls (the panel sits to the right
# of its search button). search(text) -> [Place] replaces the real service
# (tests); without it and with FIELDSHIFT_OFFLINE=1 the search says it is
# not available
class MapSearch(QtWidgets.QFrame):

    # internal: (int request number, list of Place or None), from the search thread
    _finished = QtCore.pyqtSignal(int, object)

    # (MapView view, MapControls controls, callable search = None)
    # builds the (closed) panel over view.widget()
    def __init__(self, view, controls, search=None):
        super().__init__(view.widget())
        self.view = view
        self.controls = controls
        self._search = search or geocode.search
        self._enabled = search is not None or os.environ.get(OFFLINE_ENV) != "1"
        self._request = 0
        self._query = ""
        self.places = []
        self.setObjectName("mapSearch")
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(WIDTH_PX)

        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText(tr("search.placeholder"))
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self._on_enter)
        self.edit.textChanged.connect(self._on_text_changed)
        self.status_label = QtWidgets.QLabel()
        self.status_label.setStyleSheet("color: #555;")
        self.status_label.setWordWrap(True)
        self.results = QtWidgets.QListWidget()
        self.results.setWordWrap(True)
        self.results.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.itemClicked.connect(lambda item: self.go_to(self.results.row(item)))
        self.results.itemActivated.connect(lambda item: self.go_to(self.results.row(item)))
        self.credit_label = QtWidgets.QLabel(geocode.ATTRIBUTION)
        self.credit_label.setStyleSheet("color: #777; font-size: 10px;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)
        for widget in (self.edit, self.status_label, self.results, self.credit_label):
            layout.addWidget(widget)
        self.status_label.hide()
        self.results.hide()
        self.hide()

        self._finished.connect(self._on_finished)
        controls.search_button.toggled.connect(self.set_open)
        view.widget().installEventFilter(self)

    # (bool opened)
    # opens the panel (focus in the text box) or closes it and removes the pin
    def set_open(self, opened):
        if self.controls.search_button.isChecked() != opened:
            self.controls.search_button.setChecked(opened)      # comes back through toggled
            return
        if opened:
            self._place()
            self.show()
            self.raise_()
            self.edit.setFocus()
            self.edit.selectAll()
        else:
            self.hide()
            self.view.clear_pin()
            self._request += 1                                  # drop a pending answer
            self.places, self._query = [], ""                   # a fresh search next time
            self.results.clear()
            self.results.hide()
            self.status_label.hide()

    # ()
    # searches the text of the box (Enter). returns True when a search started
    def search(self):
        text = " ".join(self.edit.text().split())
        if len(text) < 2:
            return False
        if not self._enabled:
            self._show_status(tr("search.offline"))
            return False
        self._query = text
        self._request += 1
        self.places = []
        self.results.clear()
        self.results.hide()
        self._show_status(tr("search.searching"))
        threading.Thread(target=self._run, args=(self._request, text), daemon=True,
                         name="map-search").start()
        return True

    # (int index)
    # takes the map to result number index, drops the pin and closes the list
    def go_to(self, index):
        if not 0 <= index < len(self.places):
            return
        place = self.places[index]
        self.view.zoom_to_extent(*padded_bbox(place.bbox))
        self.view.show_pin(place.lon, place.lat)
        self.results.hide()
        self.status_label.setText(place.name)
        self.status_label.show()
        self._place()

    def _run(self, request, text):
        try:
            result = self._search(text)
        except Exception:
            result = None
        self._finished.emit(request, result)

    def _on_finished(self, request, result):
        if request != self._request:
            return                                  # another search, or closed
        if result is None:
            self._show_status(tr("search.failed"))
        elif not result:
            self._show_status(tr("search.none", text=self._query))
        else:
            self.places = list(result)
            self.status_label.hide()
            self.results.clear()
            for place in self.places:
                self.results.addItem(place.name)
            self.results.setFixedHeight(self._list_height())
            self.results.show()
            self.results.setCurrentRow(0)
            self._place()

    # height that shows every result with its name wrapped over several lines
    # (names are long: street, district, region, postcode, country)
    def _list_height(self):
        metrics = self.results.fontMetrics()
        width = WIDTH_PX - 16 - 24                       # panel margins and list padding
        total = 6
        for place in self.places:
            rect = metrics.boundingRect(0, 0, width, 1000, QtCore.Qt.TextFlag.TextWordWrap, place.name)
            total += rect.height() + 14                  # item padding
        return min(total, MAX_LIST_HEIGHT_PX)

    # Enter: the first result when the list is for this very text, else search
    def _on_enter(self):
        text = " ".join(self.edit.text().split())
        if self.places and text == self._query:
            self.go_to(max(0, self.results.currentRow()))
        else:
            self.search()

    def _on_text_changed(self, _text):
        if " ".join(self.edit.text().split()) != self._query:
            self.results.hide()
            self.places = []
            self._place()

    def _show_status(self, text):
        self.status_label.setText(text)
        self.status_label.show()
        self.results.hide()
        self._place()

    # puts the panel to the right of the search button
    def _place(self):
        self.adjustSize()
        button, controls = self.controls.search_button, self.controls
        top = controls.y() + button.y()
        self.move(controls.x() + controls.width() + GAP_PX, top)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.set_open(False)
            event.accept()
        elif event.key() == QtCore.Qt.Key.Key_Down and self.results.isVisible():
            self.results.setCurrentRow(min(self.results.currentRow() + 1, self.results.count() - 1))
            event.accept()
        elif event.key() == QtCore.Qt.Key.Key_Up and self.results.isVisible():
            self.results.setCurrentRow(max(self.results.currentRow() - 1, 0))
            event.accept()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if (watched is self.parentWidget() and event.type() == QtCore.QEvent.Type.Resize
                and not self.isHidden()):
            self._place()
        return False
