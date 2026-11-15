"""Dialog to choose a field and the analyses to run on it, and the progress
window that runs them."""

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

from fieldshift.analysis import ANALYSES
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets
from fieldshift.ui.dialogs import CenteredDialog
from fieldshift.ui.fields_data import color_icon

# PLACEHOLDER: pause (ms) between progress steps, to show how loading data
# will feel. the real analyses will report their own progress
PLACEHOLDER_STEP_MS = 350
# how often (ms) the progress window checks whether the running analysis finished
POLL_MS = 50


# asks for one field (combo box) and one or more analyses (checkboxes).
# "Analyze" stays disabled until at least one analysis is checked
class AnalyzeDialog(CenteredDialog):

    # (FieldsManager fields, str layer_id = None, QWidget parent = None)
    # lists the fields; layer_id is the field selected at the start
    def __init__(self, fields, layer_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("analysis.dialog_title"))
        self.setMinimumWidth(480)

        self.field_combo = QtWidgets.QComboBox()
        for lid in fields.layer_ids():
            field = fields.field(lid)
            self.field_combo.addItem(color_icon(field.color), field.name, lid)
        if layer_id is not None and self.field_combo.findData(layer_id) >= 0:
            self.field_combo.setCurrentIndex(self.field_combo.findData(layer_id))

        choose = QtWidgets.QGroupBox(tr("analysis.choose"))
        rows = QtWidgets.QVBoxLayout(choose)
        self.checks = {}
        for analysis in ANALYSES:
            check = QtWidgets.QCheckBox(tr(analysis.title_key))
            font = check.font()
            font.setBold(True)
            check.setFont(font)
            check.toggled.connect(self._update_run_button)
            about = QtWidgets.QLabel(tr(analysis.description_key))
            about.setWordWrap(True)
            about.setStyleSheet("color: #555; margin-left: 22px; margin-bottom: 6px; margin-top: 5px")
            rows.addWidget(check)
            rows.addWidget(about)
            self.checks[analysis.id] = check

        #note = QtWidgets.QLabel(tr("analysis.placeholder_note"))
        #note.setWordWrap(True)
        #note.setStyleSheet("color: #8a6d00; background: #fff8e1; border-radius: 4px; padding: 6px;")

        buttons = QtWidgets.QDialogButtonBox()
        buttons.addButton(tr("common.cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self.run_button = buttons.addButton(tr("analysis.run"),
                                            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.run_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow(tr("analysis.field_label"), self.field_combo)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(choose)
        #layout.addWidget(note)
        layout.addWidget(buttons)
        self._update_run_button()

    # ()
    # layer id of the chosen field
    def layer_id(self):
        return self.field_combo.currentData()

    # ()
    # ids of the checked analyses, in the order of ANALYSES
    def analysis_ids(self):
        return [a.id for a in ANALYSES if self.checks[a.id].isChecked()]

    # (list ids)
    # checks exactly these analyses
    def set_analyses(self, ids):
        for analysis_id, check in self.checks.items():
            check.setChecked(analysis_id in ids)

    def _update_run_button(self, *_):
        self.run_button.setEnabled(bool(self.analysis_ids()))


# runs the chosen analyses on a field, showing each step in a progress bar.
# exec() returns Accepted with results() filled, or Rejected if cancelled
class AnalysisProgress(CenteredDialog):

    # (Field field, list analyses, QWidget parent = None)
    # prepares the steps; they start when the dialog is shown
    def __init__(self, field, analyses, parent=None):
        super().__init__(parent)
        self.field = field
        self.analyses = list(analyses)
        self._results = []
        self._steps = []                 # (text, analysis or None to run it)
        for analysis in self.analyses:
            name = tr(analysis.short_key)
            for source in analysis.sources:
                self._steps.append((tr("analysis.step.download", analysis=name,
                                       source=source.name), None))
            self._steps.append((tr("analysis.step.process", analysis=name), analysis))
            self._steps.append((tr("analysis.step.recommend", analysis=name), None))
        self._next = 0
        self._cancelled = False
        # analyses run in this worker thread (plain Python, no Qt); a timer
        # on the GUI thread collects each result, so no Qt call ever happens
        # in the worker (that raced with the window closing)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analysis")
        self._future = None
        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self._collect)

        self.setWindowTitle(tr("analysis.progress_title", field=field.name))
        self.setMinimumWidth(420)
        self.step_label = QtWidgets.QLabel(" ")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, len(self._steps))
        cancel = QtWidgets.QPushButton(tr("common.cancel"))
        cancel.clicked.connect(self.reject)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(cancel)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.step_label)
        layout.addWidget(self.bar)
        layout.addLayout(row)
        QtCore.QTimer.singleShot(0, self._step)

    # ()
    # one AnalysisResult per analysis, in order (empty until finished)
    def results(self):
        return list(self._results)

    def _step(self):
        if self._cancelled:
            return
        if self._next >= len(self._steps):
            self._pool.shutdown(wait=False)
            self.accept()
            return
        text, analysis = self._steps[self._next]
        self.step_label.setText(text)
        if analysis is not None:
            # analyses may download data and simulate (seconds): they run in
            # the worker so the window keeps moving; _collect picks the result
            self._future = self._pool.submit(analysis.run, self.field)
            self._poll.start()
            return
        self._advance()

    def _advance(self):
        self._next += 1
        self.bar.setValue(self._next)
        QtCore.QTimer.singleShot(PLACEHOLDER_STEP_MS, self._step)

    def _collect(self):
        if self._future is None or not self._future.done():
            return
        self._poll.stop()
        future, self._future = self._future, None
        if self._cancelled:
            return
        try:
            self._results.append(future.result())
        except Exception:                           # an analysis bug must not hang the window
            traceback.print_exception(future.exception(), file=sys.stderr)
        self._advance()

    def reject(self):
        self._cancelled = True                       # the pending step does nothing
        self._poll.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._results = []
        super().reject()
