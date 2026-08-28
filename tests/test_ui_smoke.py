from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QBoxLayout, QCalendarWidget, QToolButton
from PySide6.QtCore import QLocale, QMimeData, QPointF, QProcess, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest

from core.models import ComparatorResult, ComparatorRow, ProgressUpdate
from ui.main_window import MainWindow


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_opens_with_phase1_disabled_until_valid(self) -> None:
        window = MainWindow()
        self.assertEqual(window.stack.count(), 3)
        self.assertEqual(window.windowTitle(), "Suite RRHH")
        self.assertFalse(window.fase1_page.generate_button.isEnabled())
        self.assertFalse(window.comparador_page.compare_button.isEnabled())
        window.close()

    def test_control_tempo_wide_and_compact_layouts(self) -> None:
        window = MainWindow()
        window.show_phase1()
        window.show()
        window.resize(1920, 1080)
        self.app.processEvents()
        page = window.fase1_page
        self.assertIs(page.main_panels_layout.itemAtPosition(0, 0).widget(), page.files_group)
        self.assertIs(page.main_panels_layout.itemAtPosition(0, 1).widget(), page.configuration_group)
        self.assertEqual(page.scroll_area.verticalScrollBar().maximum(), 0)

        window.resize(1000, 760)
        self.app.processEvents()
        self.assertIs(page.main_panels_layout.itemAtPosition(1, 0).widget(), page.configuration_group)
        self.assertTrue(page.action_card.isVisible())
        self.assertTrue(page.progress_group.isVisible())
        window.close()

    def test_comparador_transitions_between_preparation_processing_and_result(self) -> None:
        window = MainWindow()
        window.show_comparador()
        window.show()
        window.resize(1920, 1080)
        self.app.processEvents()
        page = window.comparador_page
        self.assertFalse(hasattr(page, "scroll_area"))
        self.assertIs(page.state_stack.currentWidget(), page.preparation_state)
        self.assertTrue(page.inputs_group.isVisible())
        self.assertEqual(page.preparation_body.direction(), QBoxLayout.LeftToRight)
        self.assertGreaterEqual(page.inputs_group.width(), 1700)
        self.assertLess(page.inputs_group.y(), 130)

        page.tempo_edit.setText("C:/Datos/tabla_tempo.xlsx")
        page.sap_edit.setText("C:/Datos/informe_sap.xls")
        self.app.processEvents()
        self.assertTrue(page.compare_button.isEnabled())
        self.assertEqual(page.tempo_file_status.text(), "Seleccionado")
        self.assertEqual(page.sap_file_status.text(), "Seleccionado")

        page._set_running(True)
        self.app.processEvents()
        self.assertIs(page.state_stack.currentWidget(), page.processing_state)
        self.assertTrue(page.cancel_button.isVisible())
        self.assertEqual(page.processing_steps_layout.direction(), QBoxLayout.LeftToRight)
        self.assertGreaterEqual(page.processing_panel.width(), 1700)
        self.assertLess(page.processing_panel.y(), 130)
        page._set_running(False)

        result = ComparatorResult(
            Path("resultado.xlsx"),
            Path("incidencias.xlsx"),
            (ComparatorRow("TIR", "80057", "Trabajador de prueba", {"H. EXTRAS": -60, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}),),
            (),
            ("TIR",),
            1.0,
            (),
        )
        page._on_success(result)
        self.app.processEvents()
        self.assertIs(page.state_stack.currentWidget(), page.result_state)
        self.assertGreaterEqual(page.preview_group.height(), 500)
        self.assertEqual(page.preview_table.rowCount(), 1)
        self.assertTrue(page.open_result_button.isVisible())

        window.resize(1000, 760)
        self.app.processEvents()
        self.assertGreaterEqual(page.preview_table.height(), 210)
        page._return_to_preparation()
        self.app.processEvents()
        self.assertEqual(page.preparation_body.direction(), QBoxLayout.TopToBottom)

        page._clear()
        self.assertEqual(page.preview_table.rowCount(), 0)
        self.assertEqual(page.tempo_edit.text(), "")
        self.assertFalse(page.open_result_button.isVisible())
        self.assertIs(page.state_stack.currentWidget(), page.preparation_state)
        window.close()

    def test_window_can_be_maximized_and_restored(self) -> None:
        window = MainWindow()
        window.showMaximized()
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        self.assertFalse(window.isFullScreen())
        window.showNormal()
        self.app.processEvents()
        self.assertFalse(window.isMaximized())
        window.close()

    def test_activity_center_uses_actual_progress_values(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        page._on_progress(ProgressUpdate(
            event="file_completed",
            message="Archivo procesado",
            completed_files=1,
            total_files=2,
            completed_units=9,
            total_units=19,
        ))
        self.assertEqual(page.progress.value(), 9)
        self.assertEqual(page.progress.maximum(), 19)
        self.assertEqual(page.activity_metrics_label.text(), "Archivos procesados: 1/2")
        window.close()

    def test_control_tempo_keyboard_navigation_is_safe(self) -> None:
        window = MainWindow()
        window.show_phase1()
        window.show()
        self.app.processEvents()
        page = window.fase1_page
        page.back_button.setFocus()
        for _ in range(8):
            QTest.keyClick(self.app.focusWidget(), Qt.Key_Tab)
            self.app.processEvents()
            self.assertIsNotNone(self.app.focusWidget())
        window.close()

    def test_control_tempo_accepts_file_explorer_drops(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        self.assertTrue(page.acceptDrops())
        self.assertTrue(page.file_list.acceptDrops())
        self.assertTrue(page.file_list.table.acceptDrops())
        self.assertTrue(page.file_list.table.viewport().acceptDrops())
        window.close()

    def test_date_calendar_uses_compact_modern_configuration(self) -> None:
        window = MainWindow()
        calendar = window.fase1_page.date_edit.calendarWidget()
        self.assertEqual(calendar.objectName(), "dateCalendar")
        self.assertFalse(calendar.isGridVisible())
        self.assertEqual(calendar.firstDayOfWeek(), Qt.Monday)
        self.assertEqual(calendar.locale().language(), QLocale.Language.Spanish)
        self.assertEqual(calendar.horizontalHeaderFormat(), QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.assertEqual(calendar.verticalHeaderFormat(), QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.assertEqual(calendar.minimumWidth(), 348)
        self.assertEqual(calendar.minimumHeight(), 300)
        window.close()

    def test_file_explorer_drop_adds_excel_to_control_tempo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            excel_file = Path(directory) / "parte.xlsx"
            excel_file.touch()
            mime_data = QMimeData()
            mime_data.setUrls([QUrl.fromLocalFile(str(excel_file))])
            event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime_data, Qt.LeftButton, Qt.NoModifier)
            window = MainWindow()
            page = window.fase1_page
            page.dropEvent(event)
            self.assertEqual(page.file_list.files, [excel_file])
            self.assertTrue(event.isAccepted())
            window.close()

    def test_file_list_shows_routes_and_allows_removing_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            excel_file = Path(directory) / "parte.xlsx"
            excel_file.touch()
            window = MainWindow()
            file_list = window.fase1_page.file_list
            file_list.restore_files([excel_file, Path(directory) / "ruta_no_disponible.xlsx"])
            self.assertEqual(file_list.table.columnCount(), 4)
            self.assertEqual(file_list.table.rowCount(), 2)
            self.assertEqual(file_list.table.item(1, 2).text(), "No disponible")
            row_remove = file_list.table.cellWidget(0, 3)
            self.assertIsInstance(row_remove, QToolButton)
            self.assertEqual(row_remove.text(), "×")
            file_list.remove_path(excel_file)
            self.assertEqual(file_list.files, [Path(directory) / "ruta_no_disponible.xlsx"])
            window.close()

    def test_shortcuts_are_disabled_while_processing(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        page._process = object()
        page._set_running(True)
        self.assertFalse(page._shortcut_actions["run"].isEnabled())
        self.assertFalse(page._shortcut_actions["open"].isEnabled())
        page._process = None
        page._set_running(False)
        window.close()

    def test_start_processing_returns_immediately_if_already_running(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        called = {"request": False}
        page._process = object()
        page._build_request = lambda: called.__setitem__("request", True)
        page._start_processing()
        self.assertFalse(called["request"])
        page._process = None
        window.close()

    def test_isolated_runner_uses_available_qprocess_statuses(self) -> None:
        self.assertIsNotNone(QProcess.CrashExit)
        self.assertIsNotNone(QProcess.ProcessError.FailedToStart)


if __name__ == "__main__":
    unittest.main()
