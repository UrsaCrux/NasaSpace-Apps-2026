"""Tests for the (placeholder) analyses and the Analyze screens."""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fieldshift import i18n  # noqa: E402
from fieldshift.analysis import ANALYSES, get_analysis  # noqa: E402
from fieldshift.analysis.models import AnalysisResult  # noqa: E402
from fieldshift.fields.store import Field  # noqa: E402
from qt_app import get_app  # noqa: E402

SQUARE = [(-70.70, -33.40), (-70.69, -33.40), (-70.69, -33.41), (-70.70, -33.41)]
FIELD = Field("Viña", tuple(SQUARE), 100.0, "2026-01-01T00:00:00+00:00", None)


def setUpModule():
    get_app()


def _texts(code):
    return json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text("utf-8"))


class AnalysesTest(unittest.TestCase):
    """Every analysis of the list returns a complete, consistent result."""

    def test_ids_are_unique_and_found(self):
        ids = [a.id for a in ANALYSES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIs(get_analysis("frost"), next(a for a in ANALYSES if a.id == "frost"))
        with self.assertRaises(KeyError):
            get_analysis("nope")

    def test_results_are_complete(self):
        for analysis in ANALYSES:
            with self.subTest(analysis=analysis.id):
                result = analysis.run(FIELD)
                self.assertIsInstance(result, AnalysisResult)
                self.assertEqual((result.analysis_id, result.field_name), (analysis.id, "Viña"))
                self.assertTrue(result.placeholder)
                series, frames = result.series, result.frames
                self.assertEqual(len(series.dates), len(series.values))
                self.assertEqual(frames.dates, series.dates)          # chart and map move together
                self.assertEqual(len(frames.grids), len(series.dates))
                for grid in frames.grids:
                    self.assertTrue(all(frames.low <= v <= frames.high for row in grid for v in row))
                self.assertGreaterEqual(len(result.metrics), 1)
                self.assertGreaterEqual(len(result.recommendations), 1)

    def test_same_field_same_numbers(self):
        for analysis in ANALYSES:
            self.assertEqual(analysis.run(FIELD), analysis.run(FIELD))

    def test_every_text_exists_in_both_languages(self):
        # keys named directly, and keys embedded in values ("month.7", "crop.wheat")
        embedded = re.compile(r"\b(?:month|crop)\.[a-z0-9_]+\b")
        en, es = _texts("en"), _texts("es")
        for analysis in ANALYSES:
            result = analysis.run(FIELD)
            keys = {analysis.title_key, analysis.short_key, analysis.description_key,
                    result.summary_key, result.series.label_key, result.frames.label_key}
            keys |= {s.variable_key for s in result.sources}
            keys |= {m.label_key for m in result.metrics}
            keys |= {r.text_key for r in result.recommendations}
            keys |= {f"analysis.priority.{r.priority}" for r in result.recommendations}
            values = [m.value for m in result.metrics] + list(result.summary_params.values())
            values += [v for r in result.recommendations for v in r.params.values()]
            for value in values:
                keys |= set(embedded.findall(str(value)))
            for key in keys:
                with self.subTest(analysis=analysis.id, key=key):
                    self.assertIn(key, en)
                    self.assertIn(key, es)


class _WithFields(unittest.TestCase):
    def setUp(self):
        from fieldshift.map import create_map_view
        from fieldshift.ui import MainWindow
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = mock.patch.dict(os.environ, {"FIELDSHIFT_FIELDS_DIR": str(Path(self._tmp.name))})
        env.start()
        self.addCleanup(env.stop)
        i18n.set_language("en")
        self.view = create_map_view("placeholder")
        self.window = MainWindow(self.view)
        self.a = self.window.fields.add("A", SQUARE)
        self.b = self.window.fields.add("B", SQUARE, color="#ff0000")


class AnalyzeDialogTest(_WithFields):
    # Status / Trends open one placeholder tab each, reused on a second click
    def test_status_and_trends_tabs(self):
        first = self.window.open_mode("status")
        self.assertIs(self.window.open_mode("status"), first)
        before = self.window.tabs.count()
        self.window.open_mode("trends")
        self.assertEqual(self.window.tabs.count(), before + 1)

    def dialog(self, layer_id=None):
        from fieldshift.ui.analyze_dialog import AnalyzeDialog
        return AnalyzeDialog(self.window.fields, layer_id)

    def test_lists_fields_and_analyses(self):
        dialog = self.dialog(self.b)
        names = [dialog.field_combo.itemText(i) for i in range(dialog.field_combo.count())]
        self.assertEqual(names, ["A", "B"])
        self.assertEqual(dialog.layer_id(), self.b)            # preselected
        self.assertEqual(list(dialog.checks), [a.id for a in ANALYSES])

    def test_needs_at_least_one_analysis(self):
        dialog = self.dialog()
        self.assertEqual(dialog.layer_id(), self.a)            # first one by default
        self.assertFalse(dialog.run_button.isEnabled())
        dialog.checks["water"].setChecked(True)
        dialog.checks["frost"].setChecked(True)
        self.assertTrue(dialog.run_button.isEnabled())
        self.assertEqual(dialog.analysis_ids(), ["frost", "water"])   # list order


class ProgressTest(_WithFields):
    def test_runs_every_analysis_in_order(self):
        from fieldshift.ui import analyze_dialog
        field = self.window.fields.field(self.a)
        with mock.patch.object(analyze_dialog, "PLACEHOLDER_STEP_MS", 0):
            progress = analyze_dialog.AnalysisProgress(
                field, [get_analysis("heat"), get_analysis("vegetation")])
            self.assertEqual(progress.exec(), progress.DialogCode.Accepted)
        self.assertEqual([r.analysis_id for r in progress.results()], ["heat", "vegetation"])
        self.assertEqual(progress.bar.value(), progress.bar.maximum())

    def test_cancel_gives_no_results(self):
        from fieldshift.qt import QtCore
        from fieldshift.ui import analyze_dialog
        progress = analyze_dialog.AnalysisProgress(self.window.fields.field(self.a), list(ANALYSES))
        QtCore.QTimer.singleShot(50, progress.reject)
        self.assertEqual(progress.exec(), progress.DialogCode.Rejected)
        self.assertEqual(progress.results(), [])


class AnalysisTabTest(_WithFields):
    def tab(self, analysis_id="frost"):
        from fieldshift.ui.analysis_tab import AnalysisTab
        field = self.window.fields.field(self.a)
        return AnalysisTab(get_analysis(analysis_id).run(field), field)

    def test_four_parts_and_example_badge(self):
        from fieldshift.qt import QtWidgets
        tab = self.tab()
        boxes = {b.title(): b for b in tab.findChildren(QtWidgets.QGroupBox)}
        self.assertEqual(set(boxes), {"Data", "Map", "Results", "Recommendations"})
        # data and map share the top row, results and recommendations the bottom one
        tab.resize(1200, 800)
        tab.show()
        get_app().processEvents()
        pos = {t: b.mapTo(tab, b.rect().topLeft()) for t, b in boxes.items()}
        self.assertLess(pos["Data"].x(), pos["Map"].x())
        self.assertEqual(pos["Data"].y(), pos["Map"].y())
        self.assertLess(pos["Results"].x(), pos["Recommendations"].x())
        self.assertGreater(pos["Results"].y(), pos["Data"].y())
        tab.hide()
        self.assertEqual(tab.example_badge.text(), "Example data")
        self.assertEqual(tab.tab_title(), "Frost · A")
        self.assertEqual(len(tab.metric_cards), len(tab.result.metrics))
        self.assertEqual(len(tab.recommendation_labels), len(tab.result.recommendations))

    def test_slider_moves_chart_map_and_labels_together(self):
        tab = self.tab()
        last = len(tab.result.series.dates) - 1
        self.assertEqual((tab.date_index(), tab.chart.cursor, tab.preview.frame), (last, last, last))
        before = tab.preview.cell_colors()
        tab.slider.setValue(6)                     # July 2024
        self.assertEqual((tab.chart.cursor, tab.preview.frame), (6, 6))
        self.assertEqual(tab.date_label.text(), "July 2024")
        self.assertIn("July 2024", tab.value_label.text())
        self.assertIn("July 2024", tab.map_title.text())
        self.assertNotEqual(tab.preview.cell_colors(), before)    # the map changed

    def test_play_moves_forward_and_wraps(self):
        tab = self.tab()
        tab.set_playing(True)
        self.assertTrue(tab._play_timer.isActive())
        tab._play_step()                           # from the last date back to the first
        self.assertEqual(tab.date_index(), 0)
        tab._play_step()
        self.assertEqual(tab.date_index(), 1)
        tab.set_playing(False)
        self.assertFalse(tab._play_timer.isActive())

    def test_values_with_keys_are_translated(self):
        i18n.set_language("es")
        self.addCleanup(i18n.set_language, "en")
        tab = self.tab("rotation")
        plan = tab.metric_cards[0][0].text()
        self.assertNotIn("crop.", plan)
        self.assertIn("→", plan)
        self.assertTrue(all("crop." not in label.text() for label in tab.recommendation_labels))

    def test_recommendations_most_urgent_first(self):
        tab = self.tab("vegetation")
        texts = [label.text() for label in tab.recommendation_labels]
        order = {"High": 0, "Medium": 1, "Low": 2}
        ranks = [next(order[p] for p in order if f">{p}<" in t) for t in texts]
        self.assertEqual(ranks, sorted(ranks))


class AnalyzeFlowTest(_WithFields):
    def run_flow(self, chosen_layer, ids):
        from fieldshift.ui import analyze_dialog
        from fieldshift.ui.analyze_dialog import AnalyzeDialog

        def accept(dialog):
            index = dialog.field_combo.findData(chosen_layer)
            dialog.field_combo.setCurrentIndex(index)
            dialog.set_analyses(ids)
            return AnalyzeDialog.DialogCode.Accepted
        with mock.patch.object(AnalyzeDialog, "exec", new=accept), \
                mock.patch.object(analyze_dialog, "PLACEHOLDER_STEP_MS", 0):
            return self.window.analyze()

    def test_analyze_button_opens_one_tab_per_analysis(self):
        bar = self.window.fields_bar
        self.assertTrue(bar.analyze_button.isEnabled())
        tabs = self.run_flow(self.b, ["frost", "rotation"])
        self.assertEqual(self.window.tabs.count(), 3)            # map + 2
        self.assertEqual([self.window.tabs.tabText(i) for i in (1, 2)],
                         ["Frost · B", "Rotation · B"])
        self.assertIs(self.window.tabs.currentWidget(), tabs[0])
        self.window._close_tab(1)
        self.window._close_tab(0)                                # the map stays
        self.assertEqual(self.window.tabs.count(), 2)
        self.assertIs(self.window.tabs.widget(0), self.window.map_splitter)

    def test_dialog_starts_on_the_checked_field(self):
        from fieldshift.ui.analyze_dialog import AnalyzeDialog
        self.window.fields.set_selected(self.b, True)
        seen = {}

        def cancel(dialog):
            seen["layer"] = dialog.layer_id()
            return AnalyzeDialog.DialogCode.Rejected
        with mock.patch.object(AnalyzeDialog, "exec", new=cancel):
            self.assertEqual(self.window.analyze(), [])
        self.assertEqual(seen["layer"], self.b)
        self.assertEqual(self.window.tabs.count(), 1)

    def test_button_disabled_without_fields_or_while_drawing(self):
        bar = self.window.fields_bar
        bar.draw_button.click()
        self.assertFalse(bar.analyze_button.isEnabled())
        bar.draw_button.click()
        self.assertTrue(bar.analyze_button.isEnabled())
        self.window.fields.remove(self.a)
        self.window.fields.remove(self.b)
        self.assertFalse(bar.analyze_button.isEnabled())
        self.assertEqual(self.window.analyze(), [])


if __name__ == "__main__":
    unittest.main()
