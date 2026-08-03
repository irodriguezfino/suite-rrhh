from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QStackedWidget, QToolBar

from core.app_info import APP_VERSION
from services.update_service import UpdateService
from ui.pages.fase1_page import Fase1Page
from ui.pages.home_page import HomePage
from ui.theme import APP_ICON
from workers.update_worker import UpdateWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Suite RRHH · Control Tempo")
        self.setMinimumSize(860, 620)
        self.resize(1120, 760)
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))

        self.stack = QStackedWidget()
        self._update_thread: QThread | None = None
        self._update_worker: UpdateWorker | None = None
        self.home_page = HomePage()
        self.fase1_page = Fase1Page()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.fase1_page)
        self.setCentralWidget(self.stack)

        self._build_toolbar()
        self.home_page.open_phase1.connect(self.show_phase1)
        self.fase1_page.back_requested.connect(self.show_home)
        self.show_home()
        QTimer.singleShot(0, self._start_update_check)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Navegación")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        title = QLabel("  Suite RRHH  ")
        title.setObjectName("toolbarTitle")
        toolbar.addWidget(title)
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("mutedLabel")
        version.setToolTip("Versión instalada de Suite RRHH")
        toolbar.addWidget(version)
        toolbar.addSeparator()

        self.home_action = QAction("Inicio", self)
        self.home_action.setShortcut("Alt+H")
        self.home_action.triggered.connect(self.show_home)
        toolbar.addAction(self.home_action)

        self.control_tempo_action = QAction("Control Tempo", self)
        self.control_tempo_action.setShortcut("Alt+1")
        self.control_tempo_action.triggered.connect(self.show_phase1)
        toolbar.addAction(self.control_tempo_action)
        toolbar.addSeparator()

        help_action = QAction("Ayuda", self)
        help_action.setShortcut("F1")
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)

        exit_action = QAction("Salir", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        toolbar.addAction(exit_action)

    def show_home(self) -> None:
        if self.stack.currentWidget() is self.fase1_page and not self.fase1_page.request_leave():
            return
        self.stack.setCurrentWidget(self.home_page)

    def show_phase1(self) -> None:
        self.stack.setCurrentWidget(self.fase1_page)

    def show_help(self) -> None:
        if self.stack.currentWidget() is self.fase1_page:
            self.fase1_page.show_context_help()
            return
        QMessageBox.information(
            self,
            "Ayuda de Control Tempo",
            "1. Añade los partes Excel.\n"
            "2. Elige la fecha y el proceso Diario o Mensual 20–20.\n"
            "3. Define el archivo de salida.\n"
            "4. Genera el Control Tempo y consulta la auditoría si es necesario.",
        )

    def _start_update_check(self) -> None:
        """Comprueba en segundo plano solo las instalaciones reales, no el desarrollo."""
        if self._update_thread is not None or not UpdateService.is_installed_copy():
            return
        self._update_thread = QThread(self)
        self._update_worker = UpdateWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.available.connect(self._on_update_available)
        self._update_worker.available.connect(self._update_thread.quit)
        self._update_worker.unavailable.connect(self._update_thread.quit)
        self._update_worker.failed.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._on_update_thread_finished)
        self._update_thread.start()

    def _on_update_thread_finished(self) -> None:
        self._update_thread = None
        self._update_worker = None

    def _on_update_available(self, update) -> None:
        if self.fase1_page.is_running:
            QMessageBox.information(
                self,
                "Actualización disponible",
                "Hay una actualización disponible, pero Control Tempo está procesando datos. "
                "Termina o cancela el proceso y vuelve a abrir Suite RRHH para instalarla.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Actualización disponible",
            f"Hay disponible Suite RRHH v{update.version}.\n\n"
            "La aplicación se cerrará, instalará la actualización y se abrirá de nuevo.\n\n"
            "¿Instalar ahora?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            UpdateService.launch_updater()
        except Exception as exc:
            QMessageBox.warning(self, "No se pudo iniciar la actualización", str(exc))
            return
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self.fase1_page.request_leave():
            event.accept()
        else:
            event.ignore()
