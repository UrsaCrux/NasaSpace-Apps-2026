"""Export window: which fields, what to include (GeoJSON, measurements,
Status, Trends, analyses) with quick presets, then a progress window that
downloads in a worker thread and writes one ZIP (fieldshift.export).
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fieldshift.analysis import ANALYSES
from fieldshift.export import ExportOptions, collect
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui import dialogs
from fieldshift.ui.dialogs import CenteredDialog

# when set to "1" (tests) the export runs at once, without the worker
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"


# the options window; options() / layer_ids() after it is accepted
class ExportDialog(CenteredDialog):

    # (FieldsManager fields, list checked = None, QWidget parent = None)
    def __init__(self, fields, checked=None, parent=None):
        super().__init__(parent)
        self.fields = fields
        self.setWindowTitle(tr("export.title"))
        self.resize(520, 560)

        self.field_list = QtWidgets.QListWidget()
        chosen = set(checked or fields.layer_ids())
        for layer_id in fields.layer_ids():
            item = QtWidgets.QListWidgetItem(fields.field(layer_id).name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, layer_id)
            item.setCheckState(QtCore.Qt.CheckState.Checked if layer_id in chosen
                               else QtCore.Qt.CheckState.Unchecked)
            self.field_list.addItem(item)
        self.field_list.setMaximumHeight(140)

        presets = QtWidgets.QHBoxLayout()
        for key in ("geojson", "status_trends", "all"):
            button = QtWidgets.QPushButton(tr(f"export.preset.{key}"))
            button.setToolTip(tr(f"export.preset.{key}_tooltip"))
            button.clicked.connect(lambda _=False, k=key: self.apply_preset(k))
            presets.addWidget(button)

        self.checks = {}
        include = QtWidgets.QGroupBox(tr("export.include"))
        grid = QtWidgets.QVBoxLayout(include)
        for key in ("geojson", "records", "status", "trends"):
            box = QtWidgets.QCheckBox(tr(f"export.part.{key}"))
            box.toggled.connect(self._update)
            grid.addWidget(box)
            self.checks[key] = box
        grid.addWidget(QtWidgets.QLabel(f"<b>{tr('export.analyses')}</b>"))
        self.analysis_checks = {}
        for analysis in ANALYSES:
            box = QtWidgets.QCheckBox(tr(analysis.title_key))
            box.toggled.connect(self._update)
            grid.addWidget(box)
            self.analysis_checks[analysis.id] = box

        self.time_label = QtWidgets.QLabel()
        self.time_label.setWordWrap(True)
        self.time_label.setStyleSheet("color: #555;")
        buttons = QtWidgets.QDialogButtonBox()
        buttons.addButton(tr("common.cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self.export_button = buttons.addButton(tr("export.go"),
                                               QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel(f"<b>{tr('export.fields')}</b>"))
        layout.addWidget(self.field_list)
        layout.addLayout(presets)
        layout.addWidget(include, 1)
        layout.addWidget(self.time_label)
        layout.addWidget(buttons)
        self.field_list.itemChanged.connect(self._update)
        self.apply_preset("geojson")

    # (str preset)
    # "geojson" (only the fields), "status_trends" or "all"
    def apply_preset(self, preset):
        for key, box in self.checks.items():
            box.setChecked(key in ("geojson", "records") or preset != "geojson")
        for box in self.analysis_checks.values():
            box.setChecked(preset == "all")
        self._update()

    # ()
    # the chosen ExportOptions
    def options(self):
        return ExportOptions(
            geojson=self.checks["geojson"].isChecked(),
            records=self.checks["records"].isChecked(),
            status=self.checks["status"].isChecked(),
            trends=self.checks["trends"].isChecked(),
            analyses=tuple(a for a, box in self.analysis_checks.items() if box.isChecked()))

    # ()
    # layer ids of the chosen fields
    def layer_ids(self):
        out = []
        for i in range(self.field_list.count()):
            item = self.field_list.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                out.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return out

    def _update(self, *_):
        options, count = self.options(), len(self.layer_ids())
        seconds = count * (5 * options.status + 30 * options.trends + 40 * len(options.analyses))
        self.time_label.setText(tr("export.fast") if options.offline_only() else
                                tr("export.slow", minutes=max(1, round(seconds / 60))))
        has_part = options.geojson or options.records or not options.offline_only()
        self.export_button.setEnabled(count > 0 and has_part)


# progress window: collects every field in a worker thread, then writes
# the ZIP (charts are drawn here, in the UI thread). result() after accept
class ExportProgress(CenteredDialog):

    # (list fields, ExportOptions options, str path, QWidget parent = None)
    def __init__(self, fields, options, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("export.title"))
        self.fields, self.options, self.path = list(fields), options, path
        self.files = []
        self._cancelled = False
        self._bundles = []
        self.label = QtWidgets.QLabel(tr("export.working"))
        self.label.setWordWrap(True)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, len(self.fields))
        cancel = QtWidgets.QPushButton(tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        layout.addWidget(cancel, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        self.resize(420, 120)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="export")
        self._future = None
        self._step_text = ""
        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(150)
        self._poll.timeout.connect(self._collect)
        QtCore.QTimer.singleShot(0, self._next)

    def _next(self):
        if self._cancelled:
            return
        index = len(self._bundles)
        if index >= len(self.fields):
            self._finish()
            return
        field = self.fields[index]

        def step(name):
            self._step_text = tr("export.step", field=field.name, part=name)
        if os.environ.get(OFFLINE_ENV) == "1":
            self._bundles.append(collect(field, self.options))
            self.bar.setValue(len(self._bundles))
            self._next()
            return
        self._future = self._pool.submit(collect, field, self.options, step,
                                         lambda: self._cancelled)
        self._poll.start()

    def _collect(self):
        if self._step_text:
            self.label.setText(self._step_text)
        if self._future is None or not self._future.done():
            return
        self._poll.stop()
        self._bundles.append(self._future.result())
        self._future = None
        self.bar.setValue(len(self._bundles))
        self._next()

    def _finish(self):
        from fieldshift.export.write import write_zip
        self.label.setText(tr("export.writing"))
        QtWidgets.QApplication.processEvents()
        try:
            self.files = write_zip(self.path, self._bundles, self.options)
        except OSError as exc:
            self.error = exc
            self.reject()
            return
        self._pool.shutdown(wait=False)
        self.accept()

    def reject(self):
        self._cancelled = True
        self._poll.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        super().reject()


# (QWidget parent, str default_name)
# asks where to save a ZIP; returns the path or None
def ask_zip_path(parent, default_name):
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, tr("export.title"), str(Path.home() / default_name), "ZIP (*.zip)")
    if not path:
        return None
    return path if path.lower().endswith(".zip") else path + ".zip"


# (QWidget parent, FieldsManager fields, list checked = None)
# the whole flow: options, where to save, progress, done message. returns
# the files written (empty when cancelled)
def export_fields(parent, fields, checked=None):
    from datetime import date
    dialog = ExportDialog(fields, checked, parent)
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return []
    path = ask_zip_path(parent, f"PACHI_export_{date.today():%Y-%m-%d}.zip")
    if path is None:
        return []
    chosen = [fields.field(i) for i in dialog.layer_ids()]
    progress = ExportProgress(chosen, dialog.options(), path, parent)
    if progress.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        error = getattr(progress, "error", None)
        if error is not None:
            dialogs.inform(parent, tr("export.title"), tr("fields.export_failed", error=error))
        return []
    dialogs.inform(parent, tr("export.title"), tr("export.done", count=len(chosen), path=path))
    return progress.files
