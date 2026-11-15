"""Crop widgets of the field dialog: the search box and the information panel.

CropSearch suggests, while typing, the varieties of the local catalogue
(fieldshift/crops/crops.json) and any plant of FAO EcoCrop that matches by
scientific name, variety/synonym or common name. CropInfoPanel shows the
chosen crop's EcoCrop picture, names and (shortened) description. Network
calls run in background threads; FIELDSHIFT_OFFLINE=1 skips them.
"""

import os
import threading

from fieldshift import crops
from fieldshift.crops import ecocrop
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtGui, QtWidgets

# set to "1" to never contact the data sources (tests, no internet)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"
# EcoCrop plants added to the suggestions
ECOCROP_SUGGESTIONS = 8
# size of the picture in the panel (cropped to fill this rectangle)
IMAGE_W, IMAGE_H = 132, 96
# longer descriptions are cut at a word and end with "..."
MAX_DESCRIPTION_CHARS = 260
# frames of the loading animation, and ms between frames
SPINNER_FRAMES = ("●○○", "○●○", "○○●", "○●○")
SPINNER_MS = 180


def _offline():
    return os.environ.get(OFFLINE_ENV) == "1"


# (str text, int limit = MAX_DESCRIPTION_CHARS)
# text cut at the last whole word before limit, ending with "..."
def shorten(text, limit=MAX_DESCRIPTION_CHARS):
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] != " ":                        # inside a word: drop the partial word
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.-–") + "..."


# (bytes data, int width, int height)
# QPixmap of the picture scaled to cover width x height and cropped to that
# rectangle around its centre; None when data is not a picture
def cropped_pixmap(data, width=IMAGE_W, height=IMAGE_H):
    pixmap = QtGui.QPixmap()
    if not data or not pixmap.loadFromData(data):
        return None
    scaled = pixmap.scaled(width, height, QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           QtCore.Qt.TransformationMode.SmoothTransformation)
    x, y = (scaled.width() - width) // 2, (scaled.height() - height) // 2
    return scaled.copy(x, y, width, height)


# runs fn() in a daemon thread and emits done(token, result, error) on the
# GUI thread; results of a cancelled call are dropped
class BackgroundCall(QtCore.QObject):
    done = QtCore.pyqtSignal(int, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._token = 0

    # (callable fn)
    # starts fn in a thread; returns the token its result will carry
    def start(self, fn):
        self._token += 1
        token = self._token
        threading.Thread(target=self._run, args=(token, fn), daemon=True).start()
        return token

    # ()
    # drops the result of the call running now
    def cancel(self):
        self._token += 1

    def _run(self, token, fn):
        try:
            result, error = fn(), ""
        except Exception as exc:
            result, error = None, f"{type(exc).__name__}: {exc}"
        if token != self._token:
            return
        try:
            self.done.emit(token, result, error)
        except RuntimeError:                       # widget already destroyed
            pass


# line edit with a dropdown of the crops that match what is typed: varieties
# of the local catalogue (any language, ignoring accents) and, once the
# EcoCrop list is loaded, EcoCrop plants by scientific, variety or common
# name. A value only counts once picked from the list (or typed exactly);
# selection_changed fires when that changes
class CropSearch(QtWidgets.QLineEdit):
    selection_changed = QtCore.pyqtSignal()

    # (str variety_id = None, QWidget parent = None, callable load_index = None)
    # load_index returns the EcoCrop list (default ecocrop.load_index, run in
    # a background thread; not called when offline)
    def __init__(self, variety_id=None, parent=None, load_index=None):
        super().__init__(parent)
        self.setPlaceholderText(tr("fields.crop_placeholder"))
        self.setClearButtonEnabled(True)
        self._results = []                         # [(id, label)]
        self._selected = None
        self._eco_index = ecocrop.loaded_index()
        self._model = QtCore.QStringListModel(self)
        self.completer_ = QtWidgets.QCompleter(self._model, self)
        self.completer_.setCompletionMode(
            QtWidgets.QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completer_.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.completer_.setMaxVisibleItems(crops.MAX_RESULTS)
        self.completer_.setWidget(self)
        self.completer_.activated.connect(self._on_activated)
        self.textEdited.connect(self._on_edited)
        if crops.is_variety(variety_id):
            self.choose(variety_id)
        self._loader = BackgroundCall(self)
        self._loader.done.connect(self._on_index)
        if self._eco_index is None and (load_index is not None or not _offline()):
            self._loader.start(load_index or ecocrop.load_index)

    # ()
    # id of the chosen crop ("peach.v1" or "ecocrop:1796"), or None
    def selected(self):
        return self._selected

    # ()
    # name to store with the choice (shown when EcoCrop is not reachable)
    def selected_name(self):
        return crops.label(self._selected) if self._selected else None

    # ()
    # labels currently offered in the dropdown
    def suggestions(self):
        return self._model.stringList()

    # ()
    # True once the EcoCrop list is available to the search
    def has_ecocrop(self):
        return self._eco_index is not None

    # (str variety_id)
    # picks a crop as if chosen from the list
    def choose(self, variety_id):
        self.setText(crops.label(variety_id))
        self._set_selected(variety_id)

    # ([(id, label)] in order)
    def _search(self, text):
        local = [(v.id, crops.label(v.id)) for v in crops.search(text)]
        if not self._eco_index:
            return local
        seen = {i for i, _ in local}
        shown_eco = {crops.ecocrop_name(i) for i in seen}
        extra = []
        for entry in ecocrop.search(text, limit=ECOCROP_SUGGESTIONS, index=self._eco_index):
            if entry.name in shown_eco:
                continue
            local_crop = crops.crop_for_ecocrop(entry.name)
            if local_crop is not None:             # a catalogue crop: offer its varieties
                for v in crops.varieties(local_crop):
                    if v.id not in seen:
                        seen.add(v.id)
                        extra.append((v.id, crops.label(v.id)))
                shown_eco.add(entry.name)
                continue
            common = ", ".join(entry.common_names[:3])
            label = (tr("crops.ecocrop_suggestion", name=entry.name, common=common) if common
                     else f"{entry.name}  (EcoCrop)")
            extra.append((f"{crops.ECOCROP_PREFIX}{entry.id}", label))
        return (local + extra)[:crops.MAX_RESULTS + ECOCROP_SUGGESTIONS]

    def _on_edited(self, text):
        self._results = self._search(text)
        self._model.setStringList([label for _, label in self._results])
        # typing the exact name of a result also chooses it
        folded = crops.fold(text)
        exact = next((i for i, label in self._results
                      if folded and folded in (crops.fold(label), crops.fold(crops.label(i)))),
                     None)
        self._set_selected(exact)
        if self._results and exact is None:
            self.completer_.complete()
        else:
            self.completer_.popup().hide()

    def _on_activated(self, text):
        if not isinstance(text, str):              # QModelIndex overload
            text = text.data()
        match = next((i for i, label in self._results if label == text), None)
        if match is not None:
            self.choose(match)

    def _on_index(self, token, entries, error):
        if not entries:
            return                                 # EcoCrop unreachable: local list only
        ecocrop.set_index(entries)
        self._eco_index = entries
        if self._selected is not None:             # names of EcoCrop choices are known now
            self.setText(crops.label(self._selected))
        elif self.hasFocus() and self.text().strip():
            self._on_edited(self.text())

    def _set_selected(self, variety_id):
        if variety_id != self._selected:
            self._selected = variety_id
            self.selection_changed.emit()


# (str variety_id)
# what to ask EcoCrop for a choice: its id (int) or scientific name, or None
def ecocrop_target(variety_id):
    number = crops.ecocrop_number(variety_id)
    return number if number is not None else crops.ecocrop_name(variety_id)


# (str|int target)
# (CropInfo, picture bytes or None) from EcoCrop; the default fetch of the panel
def fetch_crop_info(target):
    info = ecocrop.get_crop(target)
    try:
        image = ecocrop.get_image(info.id)
    except Exception:                              # a missing picture is not an error
        image = None
    return info, image


# box under the crop search: EcoCrop picture (cropped rectangle), scientific
# and common names and a shortened description of the chosen crop. Hidden
# while no crop is chosen; shows an animation while it loads and a short
# message when EcoCrop has nothing (or cannot be reached)
class CropInfoPanel(QtWidgets.QFrame):

    # (QWidget parent = None, callable fetch = None)
    # fetch(target) -> (CropInfo, image bytes) replaces fetch_crop_info
    def __init__(self, parent=None, fetch=None):
        super().__init__(parent)
        self.fetch = fetch
        self.setObjectName("cropInfo")
        self.setStyleSheet("#cropInfo { background: #f7f9f4; border: 1px solid #c9d6bd;"
                           " border-radius: 6px; }")
        self.image_label = QtWidgets.QLabel()
        self.image_label.setFixedSize(IMAGE_W, IMAGE_H)
        self.image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #e3e8dc; color: #7a8670; border-radius: 4px;")
        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet("font-weight: bold; font-style: italic; font-size: 14px;")
        self.name_label.setWordWrap(True)
        self.common_label = QtWidgets.QLabel()
        self.common_label.setStyleSheet("color: #3d5a2a;")
        self.common_label.setWordWrap(True)
        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop
                                            | QtCore.Qt.AlignmentFlag.AlignLeft)
        self.source_label = QtWidgets.QLabel()
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setStyleSheet("color: #777; font-size: 11px;")

        text = QtWidgets.QVBoxLayout()
        text.setSpacing(2)
        for w in (self.name_label, self.common_label, self.description_label, self.source_label):
            text.addWidget(w)
        text.addStretch(1)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.image_label, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)

        self._state = "empty"
        self._variety = None
        self._call = BackgroundCall(self)
        self._call.done.connect(self._on_loaded)
        self._spinner_step = 0
        self._spinner = QtCore.QTimer(self)
        self._spinner.setInterval(SPINNER_MS)
        self._spinner.timeout.connect(self._animate)
        self.setVisible(False)

    # ()
    # "empty" (hidden), "loading", "ready" or "missing"
    def state(self):
        return self._state

    # (str variety_id)
    # shows the information of a crop (None hides the panel)
    def show_crop(self, variety_id):
        self._call.cancel()
        self._variety = variety_id
        target = ecocrop_target(variety_id) if variety_id else None
        if target is None:
            self._spinner.stop()
            self._state = "empty"
            self.setVisible(False)
            return
        self.setVisible(True)
        self._show_names(variety_id, None)
        self.image_label.setPixmap(QtGui.QPixmap())
        self.image_label.setText("")
        self.description_label.setText("")
        self.description_label.setToolTip("")
        self.source_label.setText("")
        if self.fetch is None and _offline():
            self._show_missing()
            return
        self._state = "loading"
        self._spinner.start()
        self._animate()
        fetch = self.fetch or fetch_crop_info
        self._call.start(lambda: fetch(target))

    # ()
    # stops a load in progress (the dialog is closing)
    def cancel(self):
        self._call.cancel()
        self._spinner.stop()

    def _animate(self):
        frame = SPINNER_FRAMES[self._spinner_step % len(SPINNER_FRAMES)]
        self._spinner_step += 1
        self.description_label.setText(f"{frame}  {tr('fields.crop_info_loading')}")
        self.description_label.setStyleSheet("color: #5b7083; font-style: italic;")

    def _on_loaded(self, token, result, error):
        self._spinner.stop()
        if not result:
            self._show_missing(error)
            return
        info, image = result
        self._state = "ready"
        self._show_names(self._variety, info)
        pixmap = cropped_pixmap(image)
        if pixmap is not None:
            self.image_label.setPixmap(pixmap)
        else:
            self.image_label.setText(tr("fields.crop_info_no_image"))
        description = info.brief or info.description
        self.description_label.setStyleSheet("")
        self.description_label.setText(shorten(description))
        full = info.description or description
        self.description_label.setToolTip(f"<p>{full}</p>" if full else "")
        self.source_label.setText(tr("fields.crop_info_source", url=info.url))

    def _show_missing(self, error=""):
        self._state = "missing"
        self.image_label.setText(tr("fields.crop_info_no_image"))
        self.description_label.setText(tr("fields.crop_info_missing"))
        self.description_label.setStyleSheet("color: #c06000;")
        self.description_label.setToolTip(error)

    # scientific name and common name(s): the catalogue name in the current
    # language for catalogue crops, else EcoCrop's first common names
    def _show_names(self, variety_id, info):
        variety = crops.variety_by_id(variety_id)
        scientific = info.scientific_name if info else (
            crops.ecocrop_name(variety_id) or crops.label(variety_id))
        if variety is not None:
            common = crops.crop_name(variety.crop)
            if info and info.common_names:
                others = [c for c in info.common_names if crops.fold(c) != crops.fold(common)]
                common = ", ".join([common] + others[:2])
        else:
            common = ", ".join(info.common_names[:3]) if info else ""
        self.name_label.setText(scientific)
        self.common_label.setText(common)
        self.common_label.setVisible(bool(common))
