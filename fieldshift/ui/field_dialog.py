"""Dialog to save a new field or edit a saved one: name, crop, colour and
zone data.

The zone data (schema.DATA_FIELDS) is loaded from the data sources of
fieldshift.fields.zone_data when the dialog opens: each source runs in its own
thread and fills its rows as soon as it answers. While a row loads it shows
a small animation and cannot be edited; Save stays disabled until every
source has answered or run out of time (each source has its own timeout_s,
at most zone_data.DEADLINE_S). A row whose source failed shows "not
available" in orange and can be typed in.
"""

import os
import threading
import time

from fieldshift import crops
from fieldshift.fields import zone_data
from fieldshift.fields.schema import (
    CROP_KEY,
    DATA_FIELDS,
    DEFAULT_COLOR,
    GROUPS,
    KIND_BOOL,
    KIND_CHOICE,
    SOURCE_MISSING,
    SOURCE_PREFILLED,
    SOURCE_USER,
    coerce_value,
    normalize_color,
    normalize_data,
)
from fieldshift.i18n import tip, tr
from fieldshift.qt import QtCore, QtGui, QtWidgets
from fieldshift.ui.crop_widgets import CropInfoPanel, CropSearch  # noqa: F401  (re-exported)
from fieldshift.ui.dialogs import CenteredDialog

# frames of the loading animation, and ms between frames
SPINNER_FRAMES = ("●○○", "○●○", "○○●", "○●○")
SPINNER_MS = 180
# looks of a row in each state
STYLE_LOADING = "background: #eef3f8; color: #5b7083;"
STYLE_MISSING = "background: #fff4e5; border: 1px solid #f0a040; color: #a05a00;"
STATUS_STYLE = {
    "loading": "color: #5b7083; font-style: italic;",
    "prefilled": "color: #777; font-style: italic;",
    "edited": "color: #1b5e20; font-weight: bold;",
    "missing": "color: #c06000; font-weight: bold;",
    "farmer": "color: #777; font-style: italic;",
}
# the dialog opens this many pixels shorter than the main window (and never
# taller than the screen); its content scrolls when it does not fit
WINDOW_MARGIN_PX = 60

# set to "1" to never contact the data sources (tests, no internet)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"


# (DataField spec, any value)
# text of a datum's value in the current language ("Clay", "6.5", "Yes");
# "—" when there is no value
def format_value(spec, value):
    if value is None:
        return "—"
    if spec.kind == KIND_CHOICE:
        return tr(f"data_fields.{spec.key}.{value}")
    if spec.kind == KIND_BOOL:
        return tr("common.yes") if value else tr("common.no")
    text = f"{value:.{spec.decimals}f}"
    return f"{text} {spec.unit}" if spec.unit else text


# (str key)
# translated name of a datum ("Soil texture")
def data_label(key):
    return tr(f"data_fields.{key}")


# runs zone_data groups in background threads and reports each result on
# the GUI thread through group_done(name, values or None, error text)
class ZoneDataLoader(QtCore.QObject):
    group_done = QtCore.pyqtSignal(str, object, str)

    # (Area area, callable fetch = zone_data.fetch_group, QObject parent = None)
    def __init__(self, area, fetch=None, parent=None):
        super().__init__(parent)
        self.area = area
        self.fetch = fetch or zone_data.fetch_group
        self._cancelled = False

    # (list groups)
    # starts one daemon thread per group
    def start(self, groups):
        for group in groups:
            threading.Thread(target=self._run, args=(group,), daemon=True,
                             name=f"zone-data-{group.name}").start()

    # ()
    # results arriving after this are dropped (the dialog was closed)
    def cancel(self):
        self._cancelled = True

    def _run(self, group):
        try:
            values, error = self.fetch(group, self.area), ""
        except Exception as exc:                   # any failure: "not available"
            values, error = None, f"{type(exc).__name__}: {exc}"
        if self._cancelled:
            return
        try:
            self.group_done.emit(group.name, values, error)
        except RuntimeError:                       # dialog already destroyed
            pass


# dialog with the details of a field. needs a name (required, unique); the
# crop is optional (a catalogue variety or an EcoCrop plant, whose picture and
# description appear under the search; text that matches no crop must be
# fixed or cleared); colour and zone data are optional.
# with field= it edits that saved field (its own name is not a duplicate),
# otherwise it asks for a new one drawn with vertices=. zone data that has no
# value yet is loaded from the data sources. For tests: fetch= replaces
# zone_data.fetch_group, crop_info_fetch= the EcoCrop crop download and
# load_ecocrop= the EcoCrop list download
class FieldDialog(CenteredDialog):

    # (FieldStore store, list vertices = None, Field field = None,
    #  QWidget parent = None, callable fetch = None, callable crop_info_fetch = None,
    #  callable load_ecocrop = None)
    # builds the dialog and starts loading the zone data
    def __init__(self, store, vertices=None, field=None, parent=None, fetch=None,
                 crop_info_fetch=None, load_ecocrop=None):
        super().__init__(parent)
        self.store = store
        self._own_name = field.name if field is not None else None
        # an existing field already has its data saved: it can be saved while
        # the empty rows still load (saving stops the loading)
        self.editing = field is not None
        vertices = list(field.vertices) if field is not None else list(vertices)
        current = normalize_data(field.data if field is not None else None)
        self._color = normalize_color(field.color if field is not None else DEFAULT_COLOR)
        self.setWindowTitle(tr("fields.edit_title") if field is not None
                            else tr("fields.save_title"))
        self.setMinimumWidth(560)

        name = field.name if field is not None else store.suggest_name(tr("fields.default_name"))
        self.name_edit = QtWidgets.QLineEdit(name)
        self.name_edit.selectAll()
        self.error_label = self._error_label()

        self.crop_search = CropSearch(current[CROP_KEY]["value"], load_index=load_ecocrop)
        self.crop_error = self._error_label()
        self.crop_info = CropInfoPanel(fetch=crop_info_fetch)

        self.color_button = QtWidgets.QPushButton(tr("fields.color_choose"))
        self.color_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                        QtWidgets.QSizePolicy.Policy.Fixed)
        self.color_button.setMinimumWidth(140)
        self.color_button.clicked.connect(self._choose_color)
        self._show_color()

        top = QtWidgets.QFormLayout()
        # macOS keeps form fields at their natural (short) width by default
        top.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        # every title and button has a tooltip from i18n/tooltips/tooltips.json
        self.tooltip_widgets = {}
        top.addRow(self._titled("field_dialog.name", tr("fields.name_label")), self.name_edit)
        top.addRow(self.error_label)
        top.addRow(self._titled("field_dialog.crop", tr("fields.crop_label")), self.crop_search)
        top.addRow(self.crop_error)
        top.addRow(self.crop_info)
        top.addRow(self._titled("field_dialog.color", tr("fields.color_label")), self.color_button)
        self._tip(self.color_button, "field_dialog.color_button")

        self._rows = {}
        data_box = QtWidgets.QGroupBox(tr("fields.data_title"))
        self._tip(data_box, "field_dialog.data_box")
        grid = QtWidgets.QGridLayout(data_box)
        hint = QtWidgets.QLabel(tr("fields.data_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        grid.addWidget(hint, 0, 0, 1, 5)
        row = 1
        for group in GROUPS:
            specs = [s for s in DATA_FIELDS if s.group == group]
            if not specs:
                continue
            title = self._titled(f"field_dialog.group.{group}", tr(f"fields.group.{group}"))
            title.setStyleSheet("font-weight: bold; margin-top: 6px;")
            grid.addWidget(title, row, 0, 1, 5)
            row += 1
            for spec in specs:
                self._add_data_row(grid, row, spec, current[spec.key])
                row += 1
        grid.setColumnStretch(1, 1)
        self.load_label = QtWidgets.QLabel()
        self.load_label.setWordWrap(True)
        self.load_label.setStyleSheet("color: #555;")
        grid.addWidget(self.load_label, row, 0, 1, 5)

        Buttons = QtWidgets.QDialogButtonBox.StandardButton
        buttons = QtWidgets.QDialogButtonBox(Buttons.Save | Buttons.Cancel)
        self.save_button = buttons.button(Buttons.Save)
        self.save_button.setText(tr("common.save"))
        self._tip(self.save_button, "field_dialog.save")
        buttons.button(Buttons.Cancel).setText(tr("common.cancel"))
        self._tip(buttons.button(Buttons.Cancel), "field_dialog.cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # everything but the buttons scrolls; Save / Cancel stay visible
        content = QtWidgets.QWidget()
        inner = QtWidgets.QVBoxLayout(content)
        inner.addLayout(top)
        inner.addWidget(data_box)
        inner.addStretch(1)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(buttons)
        content_width = content.sizeHint().width() + \
            self.scroll_area.verticalScrollBar().sizeHint().width() + 24
        self.resize(max(self.minimumWidth(), content_width), self.default_height())

        self.name_edit.textChanged.connect(self._validate)
        self.crop_search.selection_changed.connect(self._validate)
        self.crop_search.selection_changed.connect(
            lambda: self.crop_info.show_crop(self.crop_search.selected()))
        self.crop_info.show_crop(self.crop_search.selected())
        self.crop_search.textEdited.connect(lambda *_: self._validate())

        self._spinner_step = 0
        self._spinner = QtCore.QTimer(self)
        self._spinner.setInterval(SPINNER_MS)
        self._spinner.timeout.connect(self._animate)
        self._pending, self._failed = {}, []
        self._started = 0.0
        self._fetch = fetch
        self._area = zone_data.area_of(vertices)
        self._reloading = {}          # key -> (loader, started, value before, state before)
        self._start_loading(vertices, fetch)
        self._validate()

    # ()
    # height the dialog opens with: the main window's height minus
    # WINDOW_MARGIN_PX, never more than the screen's free height (the
    # screen's when there is no main window)
    def default_height(self):
        parent = self.parentWidget()
        screen = (parent.screen() if parent is not None else None) or \
            QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen is not None else 800
        if parent is not None:
            wanted = parent.window().height() - WINDOW_MARGIN_PX
        else:
            wanted = available - WINDOW_MARGIN_PX
        return max(300, min(wanted, available - WINDOW_MARGIN_PX // 2))

    # ()
    # the name typed, without surrounding spaces
    def name(self):
        return self.name_edit.text().strip()

    # ()
    # the chosen colour as "#rrggbb" (grey when none was chosen)
    def color(self):
        return self._color

    # ()
    # id of the chosen crop variety, or None
    def crop(self):
        return self.crop_search.selected()

    # ()
    # True while some data source has not answered yet
    def is_loading(self):
        return bool(self._pending) or bool(self._reloading)

    # ()
    # the data: {key: {"value", "source"[, "prefilled"]}} for DATA_FIELDS,
    # plus CROP_KEY
    def data(self):
        result = {}
        for key, row in self._rows.items():
            value = self._value(row)
            if row["state"] == "edited" and value is not None:
                source = SOURCE_USER
            elif value is not None:
                source = SOURCE_PREFILLED if row["prefilled"] is not None else SOURCE_USER
            else:
                source = SOURCE_MISSING
            item = {"value": value, "source": source}
            if row["prefilled"] is not None:
                item["prefilled"] = row["prefilled"]
            result[key] = item
        crop = self.crop()
        result[CROP_KEY] = {"value": crop, "source": SOURCE_USER if crop else SOURCE_MISSING}
        if crops.ecocrop_number(crop) is not None:
            result[CROP_KEY]["name"] = self.crop_search.selected_name()
        return result

    # (str key)
    # True when the user changed this datum (it is not the loaded one)
    def is_modified(self, key):
        return self._rows[key]["state"] == "edited"

    # (str key)
    # state of a row: loading, prefilled, edited, missing or farmer
    def row_state(self, key):
        return self._rows[key]["state"]

    # (str key, any value)
    # sets a datum as if the user had typed it (marks it edited)
    def set_value(self, key, value):
        row = self._rows[key]
        self._write(row, value)
        self._set_state(row, "edited")

    # (str key)
    # downloads this datum again from its data source (the cache is skipped)
    # and replaces the row's value with it; a failure keeps the value there
    def reload_value(self, key):
        row, group = self._rows[key], zone_data.group_of(key)
        if group is None or key in self._reloading or row["state"] == "loading":
            return
        before = (self._value(row), row["state"])
        if os.environ.get(OFFLINE_ENV) == "1" and self._fetch is None:
            self._finish_reload_failed(row, before, tr("fields.data_missing_hint"))
            return
        fetch = self._fetch or (lambda g, a: zone_data.fetch_group(g, a, refresh=True))
        loader = ZoneDataLoader(self._area, fetch, self)
        loader.group_done.connect(lambda _name, values, error, key=key:
                                  self._finish_reload(key, values, error))
        self._reloading[key] = (loader, time.monotonic(), before, group)
        self._set_state(row, "loading")
        self._spinner.start()
        self._animate()
        loader.start([group])
        self._update_load_label()
        self._validate()

    # (str key)
    # True while that datum is being downloaded again
    def is_reloading(self, key):
        return key in self._reloading

    def _finish_reload(self, key, values, error):
        entry = self._reloading.pop(key, None)
        if entry is None:                          # stopped or timed out before
            return
        loader, _started, before, _group = entry
        loader.cancel()
        row = self._rows[key]
        value = (values or {}).get(key)
        if value is not None:
            row["prefilled"] = value
            self._write(row, value)
            self._set_state(row, "prefilled")
            row["status"].setToolTip(tr("fields.data_reloaded"))
        else:
            self._finish_reload_failed(row, before, error or tr("fields.data_missing_hint"))
        self._after_answer()

    def _finish_reload_failed(self, row, before, error):
        value, state = before
        self._write(row, value)
        self._set_state(row, state if value is not None else "missing")
        row["status"].setToolTip(tr("fields.data_reload_failed", error=error))

    # (str key)
    # puts the loaded value back and marks the datum as not edited
    def reset_value(self, key):
        row = self._rows[key]
        self._write(row, row["prefilled"])
        self._set_state(row, self._idle_state(row))

    # refuses to close with Save while something is invalid or loading
    def accept(self):
        if self._problems():
            return
        if self.is_loading():                       # editing: stop and keep what there is
            self.stop_loading()
        super().accept()

    # ()
    # stops waiting for the data sources: rows still loading become "not
    # available" (their late answers are ignored)
    def stop_loading(self):
        for key in list(self._reloading):
            self._finish_reload(key, None, "")
        for group in self._pending.values():
            for key in group.keys:
                row = self._rows[key]
                if row["state"] == "loading":
                    self._set_state(row, "missing")
        self._pending.clear()
        self._loader_cancel()
        self._spinner.stop()
        self._update_load_label()
        self._validate()

    # stops the threads' results from reaching a closed dialog
    def done(self, result):
        self._loader_cancel()
        self._spinner.stop()
        self.crop_info.cancel()
        super().done(result)

    # -- loading -----------------------------------------------------------

    # (Row row)
    # True when the row has no value and nothing to restore: it must be loaded
    def _needs_loading(self, row):
        return row["prefilled"] is None and self._value(row) is None

    def _start_loading(self, vertices, fetch):
        # only sources with a row still empty are asked, and only the empty
        # rows wait for them (rows with a value keep it)
        groups = [g for g in zone_data.SOURCE_GROUPS
                  if any(self._needs_loading(self._rows[k]) for k in g.keys)]
        self._loader = None
        if not groups:
            self._update_load_label()
            return
        empty = [self._rows[k] for g in groups for k in g.keys
                 if self._needs_loading(self._rows[k])]
        if os.environ.get(OFFLINE_ENV) == "1" and fetch is None:
            for row in empty:
                self._set_state(row, "missing")
            self._update_load_label()
            return
        self._pending = {g.name: g for g in groups}
        self._total = len(groups)
        for row in empty:
            self._set_state(row, "loading")
        self._loader = ZoneDataLoader(zone_data.area_of(vertices), fetch, self)
        self._loader.group_done.connect(self._on_group_done)
        self._started = time.monotonic()
        self._spinner.start()
        self._animate()
        self._loader.start(groups)
        self._update_load_label()

    def _loader_cancel(self):
        if self._loader is not None:
            self._loader.cancel()

    def _on_group_done(self, name, values, error):
        group = self._pending.pop(name, None)
        if group is None:                          # late answer after the deadline
            return
        if values is None:
            self._failed.append(group.title or name)
        for key in group.keys:
            row = self._rows[key]
            value = (values or {}).get(key)
            if value is not None:
                row["prefilled"] = value
            if row["state"] != "loading":          # already had a value: keep it
                self._set_state(row, row["state"])  # (shows "restore" if now possible)
                continue
            self._write(row, value)
            self._set_state(row, "prefilled" if value is not None else "missing")
            if error:
                row["status"].setToolTip(error)
        self._after_answer()

    # gives up on the sources that ran out of time (their late answers are
    # ignored); called with every animation frame
    def _check_timeouts(self):
        elapsed = time.monotonic() - self._started
        late = [g for g in self._pending.values()
                if elapsed >= min(g.timeout_s, zone_data.DEADLINE_S)]
        for group in late:
            del self._pending[group.name]
            self._failed.append(group.title or group.name)
            for key in group.keys:
                row = self._rows[key]
                if row["state"] == "loading":
                    self._set_state(row, "missing")
                    row["status"].setToolTip(tr("fields.data_missing_hint"))
        if late:
            self._after_answer()

    def _after_answer(self):
        if not self._pending and self._loader is not None:
            self._loader_cancel()
        if not self._pending and not self._reloading:
            self._spinner.stop()
        self._update_load_label()
        self._validate()

    def _update_load_label(self):
        if self._pending:
            done = self._total - len(self._pending)
            key = "fields.data_status_loading_edit" if self.editing else "fields.data_status_loading"
            self.load_label.setText(tr(key, done=done, total=self._total))
        elif self._failed:
            self.load_label.setText(tr("fields.data_status_partial",
                                       names=", ".join(self._failed)))
        elif self._loader is not None:
            self.load_label.setText(tr("fields.data_status_done"))
        self.load_label.setVisible(bool(self.load_label.text()))

    def _animate(self):
        if self._pending:
            self._check_timeouts()
        for key, (_loader, started, _before, group) in list(self._reloading.items()):
            if time.monotonic() - started >= min(group.timeout_s, zone_data.DEADLINE_S):
                self._finish_reload(key, None, tr("fields.data_missing_hint"))
        frame = SPINNER_FRAMES[self._spinner_step % len(SPINNER_FRAMES)]
        self._spinner_step += 1
        text = f"{frame}  {tr('fields.data_loading')}"
        for row in self._rows.values():
            if row["state"] == "loading":
                self._show_placeholder(row, text)

    # -- colour ------------------------------------------------------------

    def _choose_color(self):
        picked = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._color), self, tr("fields.color_choose_title"))
        if picked.isValid():
            self._color = normalize_color(picked.name())
            self._show_color()

    def _show_color(self):
        dark = QtGui.QColor(self._color).lightness() < 140
        self.color_button.setStyleSheet(
            f"QPushButton {{ background: {self._color}; color: {'white' if dark else 'black'};"
            " border: 1px solid #777; border-radius: 4px; padding: 5px 14px; }")

    # -- data rows ---------------------------------------------------------

    def _add_data_row(self, grid, row_index, spec, item):
        editor, widget = self._make_editor(spec)
        status = QtWidgets.QLabel()
        reset = QtWidgets.QToolButton()
        reset.setText("↺")
        self._tip(reset, "field_dialog.reset_button", unique=False)
        # downloads this datum again (only data that comes from a source)
        reload = QtWidgets.QToolButton()
        reload.setText("⬇")
        self._tip(reload, "field_dialog.reload_button", unique=False)

        # Parent the widgets to data_box first so setVisible(True) never
        # flashes them as top-level windows.
        grid.addWidget(self._titled(f"field_dialog.data.{spec.key}", data_label(spec.key)),
                       row_index, 0)
        grid.addWidget(widget, row_index, 1)
        grid.addWidget(status, row_index, 2)
        grid.addWidget(reset, row_index, 3)
        grid.addWidget(reload, row_index, 4)

        reload.setVisible(zone_data.group_of(spec.key) is not None)
        reload.clicked.connect(lambda: self.reload_value(spec.key))
        row = {"spec": spec, "editor": editor, "status": status, "reset": reset,
               "reload": reload,
               "state": None, "writing": False, "prefilled": item.get("prefilled")}
        self._rows[spec.key] = row
        self._write(row, item["value"])
        state = ("edited" if item["source"] == SOURCE_USER and row["prefilled"] is not None
                 else self._idle_state(row) if item["value"] is None
                 else "prefilled" if row["prefilled"] is not None else "edited")
        self._set_state(row, state)

        reset.clicked.connect(lambda: self.reset_value(spec.key))
        if isinstance(editor, QtWidgets.QLineEdit):
            editor.textEdited.connect(lambda *_: self._on_user_edit(spec.key))
        else:
            editor.activated.connect(lambda *_: self._on_user_edit(spec.key))

    # the editor of a datum and the widget to put in the grid (the editor
    # plus its unit, for numbers)
    def _make_editor(self, spec):
        if spec.kind in (KIND_CHOICE, KIND_BOOL):
            box = QtWidgets.QComboBox()
            box.addItem("", None)                      # "no value" (and placeholder text)
            if spec.kind == KIND_CHOICE:
                for option in spec.options:
                    box.addItem(tr(f"data_fields.{spec.key}.{option}"), option)
            else:
                box.addItem(tr("common.yes"), True)
                box.addItem(tr("common.no"), False)
            box.setMinimumWidth(200)
            return box, box
        edit = QtWidgets.QLineEdit()
        validator = QtGui.QDoubleValidator(spec.minimum, spec.maximum, spec.decimals, edit)
        validator.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(QtCore.QLocale.c())       # "6.5", not "6,5"
        edit.setValidator(validator)
        edit.setMinimumWidth(140)
        widget = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(widget)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        unit = QtWidgets.QLabel(spec.unit)
        unit.setMinimumWidth(70)
        unit.setStyleSheet("color: #555;")
        h.addWidget(unit)
        return edit, widget

    # writes a value into the editor without counting it as a user edit
    def _write(self, row, value):
        editor, spec = row["editor"], row["spec"]
        row["writing"] = True
        try:
            if isinstance(editor, QtWidgets.QLineEdit):
                editor.setText("" if value is None else f"{value:.{spec.decimals}f}")
            else:
                index = editor.findData(value) if value is not None else 0
                editor.setCurrentIndex(max(index, 0))
        finally:
            row["writing"] = False

    def _value(self, row):
        editor, spec = row["editor"], row["spec"]
        if isinstance(editor, QtWidgets.QLineEdit):
            try:
                return coerce_value(spec, float(editor.text().replace(",", ".")))
            except ValueError:
                return None
        return editor.currentData()

    def _on_user_edit(self, key):
        row = self._rows[key]
        if not row["writing"]:
            empty = self._value(row) is None
            self._set_state(row, self._idle_state(row) if empty and row["prefilled"] is None
                            else "edited")

    # state of a row the user did not edit: farmer-only data, or missing
    def _idle_state(self, row):
        if row["prefilled"] is not None:
            return "prefilled"
        return "missing" if row["spec"].key in zone_data.FETCHED_KEYS else "farmer"

    def _set_state(self, row, state):
        row["state"] = state
        editor, status = row["editor"], row["status"]
        texts = {"loading": tr("fields.data_loading") + "…",
                 "prefilled": tr("fields.data_prefilled"), "edited": tr("fields.data_edited"),
                 "missing": tr("fields.data_missing"), "farmer": tr("fields.data_farmer")}
        status.setText(texts[state])
        status.setStyleSheet(STATUS_STYLE[state])
        status.setToolTip(tr("fields.data_missing_hint") if state == "missing" else "")
        editor.setEnabled(state != "loading")
        if "reload" in row:
            row["reload"].setEnabled(state != "loading")
        if state == "loading":
            editor.setStyleSheet(STYLE_LOADING)
        elif state == "missing" and self._value(row) is None:
            editor.setStyleSheet(STYLE_MISSING)
            self._show_placeholder(row, tr("fields.data_missing"))
        else:
            editor.setStyleSheet("")
            self._show_placeholder(row, "")
        row["reset"].setVisible(state == "edited" and row["prefilled"] is not None)

    # text shown in an editor that has no value (loading animation, "not
    # available"...)
    def _show_placeholder(self, row, text):
        editor = row["editor"]
        if isinstance(editor, QtWidgets.QLineEdit):
            editor.setPlaceholderText(text)
        else:
            editor.setItemText(0, text)

    # -- tooltips ----------------------------------------------------------

    # (str key, str text)
    # a QLabel with text and the tooltip of key
    def _titled(self, key, text):
        return self._tip(QtWidgets.QLabel(text), key)

    # (QWidget widget, str key, bool unique = True)
    # gives widget the tooltip of key (fieldshift.i18n.tip) and returns it
    def _tip(self, widget, key, unique=True):
        widget.setToolTip(tip(key))
        if unique:
            self.tooltip_widgets[key] = widget
        return widget

    # -- validation --------------------------------------------------------

    def _error_label(self):
        label = QtWidgets.QLabel()
        label.setStyleSheet("color: #b00020;")
        label.setWordWrap(True)
        label.setVisible(False)
        return label

    # list of what prevents saving now: "name", "crop", "loading"
    def _problems(self):
        problems = []
        if self.store.name_problem(self.name_edit.text(), ignore=self._own_name) is not None:
            problems.append("name")
        if self.crop() is None and self.crop_search.text().strip():
            problems.append("crop")              # typed text that is not a crop
        if self.is_loading() and not self.editing:
            problems.append("loading")
        return problems

    def _validate(self):
        problem = self.store.name_problem(self.name_edit.text(), ignore=self._own_name)
        messages = {"empty": tr("fields.error_empty"),
                    "duplicate": tr("fields.error_duplicate", name=self.name())}
        self.error_label.setText(messages.get(problem, ""))
        self.error_label.setVisible(problem is not None)     # no empty gap
        text = self.crop_search.text().strip()
        if self.crop() is None and text and not self.crop_search.suggestions():
            self.crop_error.setText(tr("fields.crop_no_match", text=text))
        else:
            self.crop_error.setText(tr("fields.crop_error"))
        self.crop_error.setVisible(self.crop() is None and bool(text))
        self.save_button.setEnabled(not self._problems())
