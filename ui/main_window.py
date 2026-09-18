from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QStackedWidget, QToolBar, QWidget, QSizePolicy

from core.app_info import APP_VERSION
from services.update_service import UpdateService
from ui.pages.fase1_page import Fase1Page
from ui.pages.comparador_tempo_page import ComparadorTempoPage
from ui.pages.home_page import HomePage
from ui.theme import APP_ICON
from workers.background_task import BackgroundTask


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Suite RRHH")
        self.setMinimumSize(860, 620)
        self.resize(1120, 760)
        if APP_ICON.exists():
            self.setWindowIcon(QIcon(str(APP_ICON)))

        # Instalar el contenedor antes de crear las páginas evita que Qt tenga
        # que reparentar QScrollArea ya pobladas al asignarlo como central.
        # En algunos equipos Windows ese reparentado nativo terminaba en una
        # violación de acceso al mostrar la ventana principal.
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self._update_thread: QThread | None = None
        self.home_page = HomePage()
        self.fase1_page = Fase1Page()
        self.comparador_page = ComparadorTempoPage()
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.fase1_page)
        self.stack.addWidget(self.comparador_page)

        self._build_toolbar()
        self.home_page.open_phase1.connect(self.show_phase1)
        self.home_page.open_comparador.connect(self.show_comparador)
        self.home_page.phase1_help.connect(self.fase1_page.show_context_help)
        self.home_page.comparator_help.connect(self.comparador_page.show_context_help)
        self.home_page.help_requested.connect(self.show_help)
        self.home_page.updates_requested.connect(lambda: self._start_update_check(manual=True))
        self.home_page.news_requested.connect(self._show_news)
        self.fase1_page.back_requested.connect(self.show_home)
        self.comparador_page.back_requested.connect(self.show_home)
        self.stack.currentChanged.connect(self._sync_navigation)
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

        self.comparador_action = QAction("Comparador de Tempo", self)
        self.comparador_action.setShortcut("Alt+2")
        self.comparador_action.triggered.connect(self.show_comparador)
        toolbar.addAction(self.comparador_action)
        self.navigation_group = QActionGroup(self)
        self.navigation_group.setExclusive(True)
        for action in (self.home_action, self.control_tempo_action, self.comparador_action):
            action.setCheckable(True)
            self.navigation_group.addAction(action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
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
        current = self.stack.currentWidget()
        if current is self.fase1_page and not self.fase1_page.request_leave():
            self._sync_navigation()
            return
        if current is self.comparador_page and not self.comparador_page.request_leave():
            self._sync_navigation()
            return
        self.stack.setCurrentWidget(self.home_page)
        self._sync_navigation()

    def show_phase1(self) -> None:
        if self.stack.currentWidget() is self.comparador_page and not self.comparador_page.request_leave():
            self._sync_navigation()
            return
        self.stack.setCurrentWidget(self.fase1_page)

    def show_comparador(self) -> None:
        if self.stack.currentWidget() is self.fase1_page and not self.fase1_page.request_leave():
            self._sync_navigation()
            return
        self.stack.setCurrentWidget(self.comparador_page)

    def _sync_navigation(self, *args) -> None:
        for action, page in ((self.home_action, self.home_page), (self.control_tempo_action, self.fase1_page), (self.comparador_action, self.comparador_page)):
            action.setChecked(self.stack.currentWidget() is page)

    def _show_news(self) -> None:
        QMessageBox.information(self, f"Novedades · v{APP_VERSION}", "• Tolerancia comienza en 0:00. Escribe 0:05 para cinco minutos o 1:30 para una hora y media. Se aplica al dejar de escribir, sin necesitar Intro.\n• El filtro Sección permite marcar varias casillas a la vez. Todas las secciones recupera la vista completa.\n• Los recuentos suman las secciones elegidas; los demás filtros y la ordenación siguen funcionando.\n• Quitar filtros restablece la selección y la tolerancia.\n\nNo se alteran cálculos ni informes guardados. Los avisos especiales se conservan y Compartir sigue exportando la comparación completa.")

    def show_help(self) -> None:
        if self.stack.currentWidget() is self.fase1_page:
            self.fase1_page.show_context_help()
            return
        if self.stack.currentWidget() is self.comparador_page:
            self.comparador_page.show_context_help()
            return
        QMessageBox.information(
            self,
            "Ayuda de Suite RRHH",
            "Selecciona una herramienta desde Inicio:\n"
            "• Control Tempo procesa partes Excel.\n"
            "• Comparador de Tempo contrasta Partes Mensuales y Tempo por código de trabajador.",
        )

    def _start_update_check(self, *, manual=False) -> None:
        """Comprueba en segundo plano solo las instalaciones reales, no el desarrollo."""
        if self._update_thread is not None or (not manual and not UpdateService.is_installed_copy()):
            return
        self.home_page.updates_button.setEnabled(False)
        self.home_page.update_status.setText("Buscando…")
        self._update_thread = BackgroundTask(lambda: UpdateService().check_for_update(), self)
        self._update_thread.finished.connect(self._on_update_thread_finished)
        self._update_thread.start()

    def _on_update_thread_finished(self) -> None:
        thread = self._update_thread
        self._update_thread = None
        self.home_page.updates_button.setEnabled(True)
        if thread is None:
            return
        # Deliver only after run() has returned, before a prompt can quit the app.
        error, value = thread.error, thread.value
        thread.deleteLater()
        if error:
            self._update_failed(error)
        elif value is None:
            self._update_unavailable()
        else:
            self._on_update_available(value)

    def _update_unavailable(self) -> None:
        self.home_page.update_status.setText("No hay una versión publicada más reciente")

    def _update_failed(self, message) -> None:
        self.home_page.update_status.setText("No se pudo comprobar. Inténtalo de nuevo.")
        self.home_page.update_status.setToolTip(message)

    def _on_update_available(self, update) -> None:
        self.home_page.update_status.setText(f"Disponible: v{update.version}")
        if not UpdateService.is_installed_copy():
            QMessageBox.information(self, "Actualización disponible", f"Hay disponible v{update.version}. Esta ejecución local no se actualizará. Abre la aplicación instalada para actualizarla.")
            return
        if self.fase1_page.is_running or self.comparador_page.is_running:
            QMessageBox.information(
                self,
                "Actualización disponible",
                "Hay una actualización disponible, pero una herramienta está procesando datos. "
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
        if self._update_thread is not None:
            QMessageBox.information(self, "Comprobación en curso", "Espera unos segundos a que termine la consulta de actualizaciones antes de salir.")
            event.ignore()
            return
        if self.fase1_page.request_leave() and self.comparador_page.request_leave():
            event.accept()
        else:
            event.ignore()
