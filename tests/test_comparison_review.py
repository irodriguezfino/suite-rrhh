"""Regression coverage for the local, read-only review workspace."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAccessible, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.models import ComparatorResult, ComparatorRow
from services.comparador_tempo_service import SAP_FIELD_BY_TEMPO, TIME_COLUMNS
from ui.pages.comparador_tempo_page import ComparadorTempoPage
from ui.theme import apply_application_style
from ui.widgets.comparison_review import calculation_text, comparison_triplet, matches_reason
from workers.comparador_tempo_runner import result_to_payload


def example_row(section="TR", code="100", name="ÁLVAREZ GARCÍA ANA"):
    pm = {field: 0 for field in TIME_COLUMNS}
    pm.update({"RUIDO": 480, "H. EXTRAS": 60, "PENOS": 30})
    tempo = {field: 0 for field in SAP_FIELD_BY_TEMPO.values()}
    tempo.update({"Trab. Dia": 450, "1016-HE": 30, "1146-PPEN": 50, "1153-PRUI": 480})
    row = ComparatorRow(
        section, code, name,
        {"H. EXTRAS": -30, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0,
         "PENOS": 20, "RUIDO": 0, "ABSENT": 0},
        trigger_fields=("Control", "H. EXTRAS", "PENOS"),
        sap_daily_work_minutes=450, sap_daily_minus_noise_minutes=-30,
        suppressed_fields=("HFJ (15%)", "BOLSA (X%)", "NOCTUR", "ABSENT"),
        pm_source_minutes=pm, tempo_source_minutes=tempo,
    )
    if section in {"ML", "MS", "MC", "MV"}:
        row = replace(row, values_minutes={**row.values_minutes, "H. EXTRAS": 0, "BOLSA (X%)": -60},
                      trigger_fields=("Control", "BOLSA (X%)", "PENOS"),
                      suppressed_fields=("HFJ (15%)", "H. EXTRAS", "NOCTUR", "ABSENT"))
    return row


class ComparisonReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for filename in ("segoeui.ttf", "segoeuib.ttf"):
            path = Path("C:/Windows/Fonts") / filename
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
        apply_application_style(cls.app)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.page = ComparadorTempoPage(settings=QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.IniFormat))
        self.page.resize(1920, 1000)
        self.page.show()
        self.app.processEvents()

    def tearDown(self):
        self.page._close_worker_detail()
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def load_rows(self, rows):
        result = ComparatorResult(Path("demo.xlsx"), Path("demo_incidencias.xlsx"), tuple(rows), (),
                                  ("TR", "ML"), 12, (), {"TR": {"pm": 50, "tempo": 49}, "ML": {"pm": 30, "tempo": 30}})
        self.page._on_success(self.page._result_from_payload(result_to_payload(result)))
        self.app.processEvents()
        return result

    def test_transport_and_explanations_use_originals(self):
        row = example_row()
        result = self.load_rows([row])
        self.assertEqual(self.page._last_result, result)
        self.assertIn("7:30 − 8:00 = −0:30", calculation_text(row, "Control"))
        self.assertIn("0:30 − 1:00 = −0:30", calculation_text(row, "H. EXTRAS"))
        self.assertIn("0:50 − 0:30 = +0:20", calculation_text(row, "PENOS"))
        self.assertIn("no son cero", calculation_text(row, "RUIDO"))
        self.assertIn("Ambos valores son cero", calculation_text(row, "HFJ (15%)"))
        self.assertIn("no están disponibles", calculation_text(replace(row, pm_source_minutes={}), "Control"))
        self.assertIn("No se comparan", calculation_text(replace(row, missing_source="Tempo"), "Control"))

    def test_special_explanations(self):
        row = example_row("ML")
        self.assertIn("consulta Bolsa", calculation_text(row, "H. EXTRAS"))
        self.assertIn("H. EXTRAS 1:00 + Bolsa 0:00 = 1:00", calculation_text(row, "BOLSA (X%)"))
        special = replace(row, section="X", red_fields=("RUIDO",))
        self.assertIn("no es una resta", calculation_text(special, "RUIDO"))
        special = replace(row, section="ADMON")
        self.assertIn("independientemente de PM", calculation_text(special, "NOCTUR"))
        absence = replace(row, red_fields=("ABSENT",), suppressed_fields=(),
                          pm_source_minutes={**row.pm_source_minutes, "ABSENT": 60},
                          tempo_source_minutes={**row.tempo_source_minutes, "1052-HDESC": 60})
        self.assertIn("incluso si es cero", calculation_text(absence, "ABSENT"))

    def test_fixed_order_combined_filters_and_stable_widths(self):
        rows = [example_row("TR", "3", "ZAPATA SOTO EVA"), example_row("ML", "2", "BENÍTEZ LÓPEZ JUAN"),
                example_row("ML", "1", "ÁLVAREZ GARCÍA ANA")]
        self.load_rows(rows)
        table = self.page.preview_table
        self.assertFalse(table.isSortingEnabled())
        self.assertEqual([row.sap_code for row in self.page._preview_rows], ["1", "2", "3"])
        table.setColumnWidth(2, 267)
        self.page.section_filter.setCurrentText("ML")
        self.page.reason_filter.setCurrentIndex(self.page.reason_filter.findData("Control"))
        self.page.worker_search.setText("ana alvarez")
        QTest.qWait(200)
        self.assertEqual([row.sap_code for row in self.page._preview_rows], ["1"])
        self.assertEqual(table.columnWidth(2), 267)
        self.assertIn("Partes Mensuales: 30 · Tempo: 30", self.page.source_count.text())
        self.page.worker_search.setText("NO EXISTE")
        QTest.qWait(200)
        self.assertEqual(table.rowCount(), 0)
        self.assertFalse(self.page.detail_button.isEnabled())
        self.assertTrue(self.page.empty_preview_label.isVisible())
        self.page._reset_preview_filters()
        self.assertEqual(table.rowCount(), 3)
        self.assertEqual(table.columnWidth(2), 267)

    def test_sticky_section_resizing_and_density(self):
        self.load_rows([example_row()])
        table = self.page.preview_table
        self.assertEqual(table.horizontalHeader().visualIndex(12), 0)
        self.assertFalse(table.frozen.isColumnHidden(12))
        table.frozen.setColumnWidth(1, 370)
        self.assertEqual(table.columnWidth(1), 370)
        table.reset_column_widths()
        self.assertEqual(table.columnWidth(1), 275)
        comfortable = table.rowHeight(0)
        self.page.compact_action.setChecked(True)
        self.assertLess(table.rowHeight(0), comfortable)
        self.assertEqual(table.rowHeight(0), table.frozen.rowHeight(0))
        self.page.compact_action.setChecked(False)
        self.assertEqual(table.rowHeight(0), comfortable)

    def test_triplets_and_relevant_fields(self):
        row = example_row()
        self.load_rows([row])
        self.page.preview_table.setCurrentCell(0, 4)
        self.page._open_worker_detail()
        panel = self.page.worker_detail
        self.assertEqual(comparison_triplet(row, "H. EXTRAS"), ("0:30", "1:00", "−0:30", "Diferencia"))
        self.assertNotIn("HFJ (15%)", panel.browser.toPlainText())
        panel.all_fields.setChecked(True)
        self.assertIn("HFJ (15%)", panel.browser.toPlainText())
        direct = replace(example_row("X"), values_minutes={"RUIDO": 480}, red_fields=("RUIDO",))
        self.assertEqual(comparison_triplet(direct, "RUIDO")[-1], "Valor a revisar")
        self.assertEqual(comparison_triplet(example_row("ML"), "BOLSA (X%)"), ("0:00", "1:00", "−1:00", "Diferencia"))
        self.assertEqual(comparison_triplet(replace(row, missing_source="Tempo"), "Control"), ("—", "—", "—", "Sin comparación"))

    def test_detail_navigation_width_escape_and_resize_without_dialog(self):
        self.load_rows([example_row(code=str(i), name=f"NOMBRE {i}") for i in range(3)])
        self.page._open_worker_detail()
        panel = self.page.worker_detail
        self.assertFalse(panel.previous_button.isEnabled())
        panel.next_button.click()
        self.assertEqual(self.page.preview_table.currentRow(), 1)
        self.assertIn("NOMBRE 1", panel.identity_label.text())
        self.page.review_splitter.setSizes([1250, 520])
        self.page._remember_detail_width()
        saved = panel.width()
        self.page.preview_table.setFocus()
        QTest.keyClick(self.page.preview_table, Qt.Key_Escape)
        self.assertTrue(panel.isHidden())
        self.page._open_worker_detail()
        self.assertAlmostEqual(panel.width(), saved, delta=3)
        self.page.resize(1280, 720)
        self.app.processEvents()
        self.assertTrue(panel.isHidden())
        self.assertIsNone(self.page._detail_dialog)
        self.assertEqual(self.page.preview_table.currentRow(), 1)
        self.page._open_worker_detail()
        self.page._dialog_detail_panel.next_button.click()
        self.assertEqual(self.page.preview_table.currentRow(), 2)
        self.assertFalse(self.page._dialog_detail_panel.next_button.isEnabled())
        self.assertIn("NOMBRE 2", self.page._dialog_detail_panel.identity_label.text())

    def test_search_is_debounced_and_unchanged_rows_are_not_rebuilt(self):
        from time import perf_counter
        started = perf_counter()
        self.load_rows([example_row(code=str(i), name=f"APELLIDO NOMBRE {i}") for i in range(1500)])
        rendered = perf_counter() - started
        timeouts = []
        self.page._search_timer.timeout.connect(lambda: timeouts.append(1))
        old_item = self.page.preview_table.item(0, 0)
        for text in ("a", "ap", "ape", "apel", "apell", "apellido"):
            self.page.worker_search.setText(text)
        QTest.qWait(250)
        self.assertEqual(len(timeouts), 1)
        self.assertIs(self.page.preview_table.item(0, 0), old_item)
        self.assertIn("apellido", self.page.active_filters.toolTip())
        self.assertTrue(self.page.active_filters.isVisible())
        self.page._reset_preview_filters()
        self.assertFalse(self.page.active_filters.isVisible())
        print(f"\nReview benchmark: 1500 rows rendered in {rendered:.3f}s; six keystrokes -> one filter pass, no cell rebuild.")

    def test_accessible_single_table_and_tab_order(self):
        self.load_rows([example_row()])
        table = self.page.preview_table
        self.page.accessible_action.setChecked(True)
        self.assertTrue(table.frozen.isHidden())
        interface = QAccessible.queryAccessibleInterface(table)
        self.assertIsNotNone(interface)
        self.assertEqual(interface.role(), QAccessible.Table)
        self.assertIn("H. EXTRAS", table.item(0, 5).data(Qt.AccessibleTextRole))
        self.assertIn("−0:30", table.item(0, 5).data(Qt.AccessibleTextRole))
        self.page.section_filter.setFocus()
        QTest.keyClick(self.page.section_filter, Qt.Key_Tab)
        self.assertIs(self.app.focusWidget(), self.page.worker_search)
        QTest.keyClick(self.page.worker_search, Qt.Key_Tab)
        self.assertIs(self.app.focusWidget(), self.page.reason_filter)
        self.page.accessible_action.setChecked(False)
        self.assertTrue(table.frozen.isVisible())

    def test_view_preferences_survive_reopening_and_filtering_preserves_order(self):
        self.load_rows([example_row("TR", "2", "ZETA ANA"), example_row("ML", "1", "ALFA BEA")])
        self.page.compact_action.setChecked(True)
        self.page.accessible_action.setChecked(True)
        self.page._settings.sync()
        other = ComparadorTempoPage(settings=QSettings(str(Path(self.directory.name) / "settings.ini"), QSettings.IniFormat))
        try:
            self.assertTrue(other.compact_action.isChecked())
            self.assertTrue(other.accessible_action.isChecked())
            self.assertTrue(other.preview_table.frozen.isHidden())
        finally:
            other.close()
            other.deleteLater()
        self.assertEqual([row.sap_code for row in self.page._preview_rows], ["1", "2"])

    def test_full_paths_available_to_keyboard_and_copy_is_explicit(self):
        from PySide6.QtWidgets import QDialog, QLineEdit, QPushButton
        self.load_rows([example_row()])
        self.page._show_source_paths()
        self.app.processEvents()
        dialog = next(d for d in self.page.findChildren(QDialog) if d.windowTitle() == "Archivos de la comprobación")
        edits = dialog.findChildren(QLineEdit)
        self.assertEqual(len(edits), 4)
        self.assertTrue(all(edit.isReadOnly() for edit in edits))
        self.assertTrue(all(edit.accessibleName() for edit in edits))
        self.assertEqual(len([b for b in dialog.findChildren(QPushButton) if b.text() == "Copiar ruta"]), 4)
        QTest.keyClick(dialog, Qt.Key_Escape)
        self.assertFalse(dialog.isVisible())

    def test_reason_filters_missing_and_red(self):
        row = example_row()
        self.assertTrue(matches_reason(row, "Control"))
        self.assertFalse(matches_reason(row, "red"))
        self.assertTrue(matches_reason(replace(row, red_fields=("ABSENT",)), "red"))
        self.assertTrue(matches_reason(replace(row, incidence_messages=("Falta fichaje de entrada",)), "marking"))
        self.assertFalse(matches_reason(replace(row, incidence_messages=("Vacaciones",)), "marking"))
        self.assertTrue(matches_reason(replace(row, missing_source="Tempo"), "only_pm"))
        self.assertTrue(matches_reason(replace(row, missing_source="Partes Mensuales"), "only_tempo"))

    def test_frozen_columns_share_model_selection_and_scroll(self):
        self.load_rows([example_row(code=str(i), name=f"APELLIDO {i:03} NOMBRE") for i in range(100)])
        table = self.page.preview_table
        self.assertIs(table.frozen.model(), table.model())
        self.assertIs(table.frozen.selectionModel(), table.selectionModel())
        table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
        table.verticalScrollBar().setValue(400)
        self.app.processEvents()
        self.assertEqual(table.frozen.x(), table.frameWidth())
        self.assertEqual(table.frozen.verticalScrollBar().value(), table.verticalScrollBar().value())
        for column in (0, 1):
            self.assertEqual(table.columnWidth(column), table.frozen.columnWidth(column))
        table.frozen.setCurrentIndex(table.model().index(20, 1))
        self.assertEqual(table.currentRow(), 20)
        self.assertEqual(table.visualRect(table.model().index(20, 4)).top(), table.frozen.visualRect(table.model().index(20, 1)).top())

    def test_detail_keyboard_and_responsive_layout(self):
        self.load_rows([example_row()])
        table = self.page.preview_table
        table.setCurrentCell(0, 4)
        table.setFocus()
        QTest.keyClick(table, Qt.Key_Return)
        self.app.processEvents()
        self.assertTrue(self.page.worker_detail.isVisible())
        self.assertIn("7:30 − 8:00", self.page.worker_detail.browser.toPlainText())
        QTest.keyClick(self.page.worker_detail.close_button, Qt.Key_Escape)
        self.app.processEvents()
        self.assertTrue(self.page.worker_detail.isHidden())
        for width, height in ((1920, 1000), (1366, 768), (1280, 720)):
            self.page.resize(width, height)
            self.app.processEvents()
            self.assertLessEqual(self.page.width(), width)
            self.assertLessEqual(self.page.height(), height)
            self.assertGreaterEqual(self.page.preview_group.height(), self.page.height() // 2)
            self.assertTrue(self.page.rect().contains(self.page.preview_group.geometry().bottomRight() + self.page.state_stack.pos()))
        self.page._open_worker_detail()
        self.app.processEvents()
        self.assertIsNotNone(self.page._detail_dialog)
        QTest.keyClick(self.page._detail_dialog, Qt.Key_Escape)
        self.app.processEvents()
        self.assertIsNone(self.page._detail_dialog)

    def test_review_space_sources_toggle_and_compact_summary(self):
        self.load_rows([example_row(code=str(i), name=f"NOMBRE {i}") for i in range(50)])
        self.page._open_worker_detail()
        self.app.processEvents()
        self.assertTrue(self.page.page_header.isHidden())
        self.assertTrue(self.page.result_context_bar.isHidden())
        height = self.page.preview_table.height()
        self.assertGreaterEqual(height, 730)
        self.assertGreaterEqual(self.page.worker_detail.browser.height(), 580)
        self.assertGreaterEqual(self.page.worker_detail.browser.width(), 500)
        self.assertEqual(self.page.worker_detail.browser.horizontalScrollBar().maximum(), 0)
        self.page.sources_action.setChecked(True)
        self.app.processEvents()
        self.assertTrue(self.page.result_context_bar.isVisible())
        self.assertLess(self.page.preview_table.height(), height)
        self.page.sources_action.setChecked(False)
        self.app.processEvents()
        self.assertEqual(self.page.preview_table.height(), height)
        self.page.resize(1280, 720)
        self.app.processEvents()
        self.assertGreaterEqual(self.page.preview_table.height(), 450)
        self.page._return_to_preparation()
        self.assertTrue(self.page.page_header.isVisible())

    def test_summary_concept_selection_and_expanded_detail(self):
        self.load_rows([example_row()])
        self.page.detail_button.click()
        self.app.processEvents()
        panel = self.page.worker_detail
        panel._choose_field(QUrl("#concept6"))  # PENOS in the shared field list.
        self.assertIn("Cálculo de PENOS", panel.browser.toPlainText())
        self.assertEqual(self.page.preview_table.currentColumn(), 9)
        panel.expand_button.click()
        self.app.processEvents()
        self.assertIsNotNone(self.page._detail_dialog)
        self.assertGreaterEqual(self.page._detail_dialog.width(), 1100)
        self.assertGreaterEqual(self.page._detail_dialog.height(), 850)
        self.assertTrue(self.page._dialog_detail_panel.expand_button.isHidden())
        QTest.keyClick(self.page._detail_dialog, Qt.Key_Escape)
        self.app.processEvents()
        self.assertIsNone(self.page._detail_dialog)
        self.assertTrue(panel.isVisible())
        self.assertEqual(self.page.preview_table.currentColumn(), 9)

    def test_capture_optional_synthetic_preview(self):
        target = os.environ.get("RRHH_REVIEW_CAPTURE")
        if not target:
            self.skipTest("Optional visual review with synthetic data")
        rows = [example_row("ML" if i < 10 else "TR", str(80000+i), f"APELLIDO {i:02} NOMBRE") for i in range(55)]
        self.load_rows(rows)
        self.page.tempo_edit.setText("C:/Datos/Partes_mensuales_septiembre.xlsx")
        self.page.sap_edit.setText("C:/Datos/Tempo_septiembre.xlsx")
        # Changing inputs may reset the result; restore it before rendering.
        self.load_rows(rows)
        self.page.resize(1920, 1000)
        self.app.processEvents()
        Path(target).mkdir(parents=True, exist_ok=True)
        self.page.grab().save(str(Path(target) / "revision.png"))
        self.page.preview_table.setCurrentCell(0, 4)
        self.page._open_worker_detail()
        self.app.processEvents()
        self.page.grab().save(str(Path(target) / "detalle.png"))
        self.page._close_worker_detail()
        self.page.resize(1280, 720)
        self.app.processEvents()
        self.page.grab().save(str(Path(target) / "compacta.png"))
