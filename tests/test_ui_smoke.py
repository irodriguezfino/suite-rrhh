from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.models import ProgressUpdate
from ui.main_window import MainWindow


class UiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_opens_with_phase1_disabled_until_valid(self) -> None:
        window = MainWindow()
        self.assertEqual(window.stack.count(), 2)
        self.assertEqual(window.windowTitle(), "Suite RRHH · Control Tempo")
        self.assertFalse(window.fase1_page.generate_button.isEnabled())
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

    def test_control_tempo_tab_order_starts_with_input(self) -> None:
        window = MainWindow()
        window.show_phase1()
        window.show()
        self.app.processEvents()
        page = window.fase1_page
        page.back_button.setFocus()
        QTest.keyClick(page.back_button, Qt.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), page.file_list.add_button)
        QTest.keyClick(page.file_list.add_button, Qt.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), page.file_list.table)
        window.close()

    def test_shortcuts_are_disabled_while_processing(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        page._thread = object()
        page._set_running(True)
        self.assertFalse(page._shortcut_actions["run"].isEnabled())
        self.assertFalse(page._shortcut_actions["open"].isEnabled())
        page._thread = None
        page._set_running(False)
        window.close()

    def test_start_processing_returns_immediately_if_already_running(self) -> None:
        window = MainWindow()
        page = window.fase1_page
        called = {"request": False}
        page._thread = object()
        page._build_request = lambda: called.__setitem__("request", True)
        page._start_processing()
        self.assertFalse(called["request"])
        page._thread = None
        window.close()


if __name__ == "__main__":
    unittest.main()
