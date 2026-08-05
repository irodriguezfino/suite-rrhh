from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QElapsedTimer, QLocale, QSettings, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QButtonGroup,
    QCalendarWidget,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.models import ProcessRequest, ProcessResult, ProgressUpdate
from fase1_recopilacion import EMPLOYMENT_MODE_ACTIVE, PROCESS_MODE_DAILY, PROCESS_MODE_MONTHLY
from ui.dialogs.details_dialog import DetailsDialog
from ui.dialogs.error_dialog import ErrorDialog
from ui.widgets.file_list_widget import FileListWidget
from workers.fase1_worker import Fase1Worker

MONTHS = ("ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE")


class Fase1Page(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self.setAcceptDrops(True)
        self._thread: QThread | None = None
        self._worker: Fase1Worker | None = None
        self._details: list[str] = []
        self._last_result: ProcessResult | None = None
        self._completed_files = 0
        self._total_files = 0
        self._settings = QSettings()
        self._shortcut_actions: dict[str, QAction] = {}
        self._elapsed_timer = QElapsedTimer()
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(1000)
        self._activity_timer.timeout.connect(self._update_elapsed_time)
        self._build_ui()
        self._install_shortcuts()
        self._restore_last_input_files()
        self._update_form_state()

    def _install_shortcuts(self) -> None:
        shortcuts = (
            ("open", "Ctrl+O", self._choose_files),
            ("output", "Ctrl+S", self._choose_output),
            ("run", "Ctrl+R", self._start_processing),
            ("details", "Ctrl+D", self._show_details),
        )
        for name, shortcut, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self._shortcut_actions[name] = action
        self._shortcut_actions["details"].setEnabled(False)

    @property
    def is_running(self) -> bool:
        return self._thread is not None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll_area)
        content = QWidget()
        self.scroll_area.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.back_button = QPushButton("← Inicio")
        self.back_button.setAccessibleName("Volver a Inicio")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button, 0, Qt.AlignLeft)
        heading_layout = QVBoxLayout()
        heading_layout.setSpacing(2)
        title = QLabel("Control Tempo")
        title.setObjectName("pageTitle")
        heading_layout.addWidget(title)
        subtitle = QLabel("Partes Excel · consulta Diario o Mensual 20–20 · recopilación auditada")
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        heading_layout.addWidget(subtitle)
        header.addLayout(heading_layout, 1)
        mode_badge = QLabel("EXCEL")
        mode_badge.setObjectName("modeBadge")
        mode_badge.setAccessibleName("Herramienta de recopilación Excel")
        header.addWidget(mode_badge, 0, Qt.AlignRight)
        layout.addLayout(header)

        self.files_group = QGroupBox("Partes de entrada")
        file_layout = QVBoxLayout(self.files_group)
        self.file_list = FileListWidget()
        self.file_list.add_button.clicked.connect(self._choose_files)
        self.file_list.files_changed.connect(self._on_files_changed)
        file_layout.addWidget(self.file_list)

        self.configuration_group = QGroupBox("Configuración")
        configuration_layout = QGridLayout(self.configuration_group)
        configuration_layout.setContentsMargins(16, 18, 16, 16)
        configuration_layout.setHorizontalSpacing(12)
        configuration_layout.setVerticalSpacing(12)

        date_panel = QFrame()
        date_panel.setObjectName("compactPanel")
        date_layout = QGridLayout(date_panel)
        date_layout.setContentsMargins(12, 10, 12, 10)
        date_layout.setHorizontalSpacing(8)
        date_heading = QLabel("Fecha de consulta")
        date_heading.setObjectName("sectionLabel")
        date_layout.addWidget(date_heading, 0, 0, 1, 2)
        date_label = QLabel("Fecha")
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setMaximumDate(QDate.currentDate())
        calendar = self.date_edit.calendarWidget()
        calendar.setObjectName("dateCalendar")
        calendar.setGridVisible(False)
        calendar.setFirstDayOfWeek(Qt.Monday)
        calendar.setLocale(QLocale(QLocale.Language.Spanish, QLocale.Country.Spain))
        calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setMinimumSize(348, 300)
        calendar.setToolTip("Usa las flechas para cambiar de mes y selecciona una fecha.")
        calendar.setAccessibleName("Calendario de fecha de consulta")
        self.date_edit.setAccessibleName("Fecha de consulta")
        self.date_edit.setAccessibleDescription("Fecha usada para filtrar altas y bajas de trabajadores.")
        self.date_edit.dateChanged.connect(self._update_period_description)
        date_label.setBuddy(self.date_edit)
        date_layout.addWidget(date_label, 1, 0)
        date_layout.addWidget(self.date_edit, 1, 1)
        self.period_label = QLabel()
        self.period_label.setObjectName("mutedLabel")
        self.period_label.setWordWrap(True)
        date_layout.addWidget(self.period_label, 2, 0, 1, 2)
        configuration_layout.addWidget(date_panel, 0, 0)

        process_panel = QFrame()
        process_panel.setObjectName("compactPanel")
        process_layout = QVBoxLayout(process_panel)
        process_layout.setContentsMargins(12, 10, 12, 10)
        process_layout.setSpacing(6)
        process_heading = QLabel("Modo de proceso")
        process_heading.setObjectName("sectionLabel")
        process_layout.addWidget(process_heading)
        self.daily_radio = QRadioButton("Diario · solo la fecha seleccionada")
        self.monthly_radio = QRadioButton("Mensual · ciclo 20–20")
        self.daily_radio.setAccessibleName("Proceso diario")
        self.monthly_radio.setAccessibleName("Proceso mensual 20–20")
        self.daily_radio.setChecked(True)
        self.process_buttons = QButtonGroup(self)
        self.process_buttons.addButton(self.daily_radio)
        self.process_buttons.addButton(self.monthly_radio)
        self.daily_radio.toggled.connect(self._update_period_description)
        self.monthly_radio.toggled.connect(self._update_period_description)
        process_layout.addWidget(self.daily_radio)
        process_layout.addWidget(self.monthly_radio)
        process_layout.addStretch(1)
        configuration_layout.addWidget(process_panel, 0, 1)

        output_panel = QFrame()
        output_panel.setObjectName("compactPanel")
        output_layout = QVBoxLayout(output_panel)
        output_layout.setContentsMargins(12, 10, 12, 10)
        output_layout.setSpacing(6)
        output_heading = QLabel("Archivo de salida")
        output_heading.setObjectName("sectionLabel")
        output_layout.addWidget(output_heading)
        output_hint = QLabel("Indica dónde guardar el Excel final.")
        output_hint.setObjectName("mutedLabel")
        output_hint.setWordWrap(True)
        output_layout.addWidget(output_hint)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("C:\\Ruta\\control_tempo.xlsx")
        self.output_edit.setAccessibleName("Archivo Excel de salida")
        self.output_edit.textChanged.connect(self._update_form_state)
        self.browse_button = QPushButton("Examinar…")
        self.browse_button.setAccessibleName("Elegir archivo de salida")
        self.browse_button.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.browse_button)
        output_layout.addLayout(output_row)
        configuration_layout.addWidget(output_panel, 1, 0, 1, 2)
        configuration_layout.setColumnStretch(0, 1)
        configuration_layout.setColumnStretch(1, 1)

        self.main_panels_layout = QGridLayout()
        self.main_panels_layout.setHorizontalSpacing(14)
        self.main_panels_layout.setVerticalSpacing(14)
        layout.addLayout(self.main_panels_layout)

        # Se crea despues del contenido para conservar un orden de tabulacion
        # natural, aunque visualmente permanezca fijo bajo el area central.
        footer = QWidget()
        footer.setObjectName("fixedFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(28, 0, 28, 20)
        footer_layout.setSpacing(8)
        outer.addWidget(footer)

        self.action_card = QFrame()
        self.action_card.setObjectName("actionCard")
        actions = QHBoxLayout(self.action_card)
        actions.setContentsMargins(14, 10, 14, 10)
        actions.setSpacing(8)
        self.summary = QLabel()
        self.summary.setObjectName("summaryLabel")
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName("Resumen de preparación")
        actions.addWidget(self.summary, 1)
        self.generate_button = QPushButton("Generar Control Tempo")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.setToolTip("Ctrl+R")
        self.generate_button.setAccessibleName("Generar Control Tempo")
        self.generate_button.clicked.connect(self._start_processing)
        self.reset_button = QPushButton("Restablecer")
        self.reset_button.clicked.connect(self._reset_form)
        self.details_button = QPushButton("Ver auditoría")
        self.details_button.setEnabled(False)
        self.details_button.clicked.connect(self._show_details)
        self.cancel_button = QPushButton("Cancelar proceso")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._request_cancel)
        actions.addWidget(self.generate_button)
        actions.addWidget(self.reset_button)
        actions.addWidget(self.details_button)
        actions.addWidget(self.cancel_button)
        footer_layout.addWidget(self.action_card)

        self.progress_group = QFrame()
        self.progress_group.setObjectName("activityCard")
        progress_layout = QGridLayout(self.progress_group)
        progress_layout.setContentsMargins(14, 12, 14, 12)
        progress_layout.setHorizontalSpacing(12)
        progress_layout.setVerticalSpacing(7)
        progress_heading = QLabel("Centro de actividad")
        progress_heading.setObjectName("sectionLabel")
        progress_layout.addWidget(progress_heading, 0, 0)
        self.activity_state_label = QLabel("Preparación pendiente")
        self.activity_state_label.setObjectName("activityPending")
        self.activity_state_label.setAccessibleName("Estado resumido de Control Tempo")
        progress_layout.addWidget(self.activity_state_label, 0, 1, 1, 2, Qt.AlignRight)
        self.status_label = QLabel("Añade partes y define la salida para comenzar.")
        self.status_label.setObjectName("statusInfo")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Estado del proceso")
        progress_layout.addWidget(self.status_label, 1, 0, 1, 3)
        from PySide6.QtWidgets import QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Sin ejecución")
        self.progress.setAccessibleName("Progreso de Control Tempo")
        progress_layout.addWidget(self.progress, 2, 0, 1, 3)
        self.activity_metrics_label = QLabel("Partes seleccionados: 0")
        self.activity_metrics_label.setObjectName("mutedLabel")
        self.activity_metrics_label.setAccessibleName("Métricas de Control Tempo")
        progress_layout.addWidget(self.activity_metrics_label, 3, 0)
        self.elapsed_label = QLabel("Tiempo transcurrido: —")
        self.elapsed_label.setObjectName("mutedLabel")
        self.elapsed_label.setAccessibleName("Tiempo transcurrido")
        progress_layout.addWidget(self.elapsed_label, 3, 1)
        self.result_actions = QHBoxLayout()
        self.open_file_button = QPushButton("Abrir Excel generado")
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_file_button.clicked.connect(self._open_output_file)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        self.open_file_button.setVisible(False)
        self.open_folder_button.setVisible(False)
        self.result_actions.addWidget(self.open_file_button)
        self.result_actions.addWidget(self.open_folder_button)
        self.result_actions.addStretch(1)
        progress_layout.addLayout(self.result_actions, 3, 2)
        progress_layout.setColumnStretch(0, 1)
        footer_layout.addWidget(self.progress_group)
        layout.addStretch(1)
        self._configure_tab_order()
        self._update_panel_layout()
        self._update_period_description()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Qt termina de componer el QScrollArea al mostrar la pagina. Fijar el
        # orden aqui evita que el pie fijo se interponga en la primera pulsacion
        # de Tab.
        self._configure_tab_order()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.file_list.add_files(paths)
            event.acceptProposedAction()

    def _configure_tab_order(self) -> None:
        QWidget.setTabOrder(self.back_button, self.file_list.add_button)
        QWidget.setTabOrder(self.file_list.add_button, self.file_list.table)
        QWidget.setTabOrder(self.file_list.table, self.file_list.remove_button)
        QWidget.setTabOrder(self.file_list.remove_button, self.file_list.clear_button)
        QWidget.setTabOrder(self.file_list.clear_button, self.date_edit)
        QWidget.setTabOrder(self.date_edit, self.daily_radio)
        QWidget.setTabOrder(self.daily_radio, self.monthly_radio)
        QWidget.setTabOrder(self.monthly_radio, self.output_edit)
        QWidget.setTabOrder(self.output_edit, self.browse_button)
        QWidget.setTabOrder(self.browse_button, self.generate_button)
        QWidget.setTabOrder(self.generate_button, self.reset_button)
        QWidget.setTabOrder(self.reset_button, self.details_button)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_panel_layout()

    def _update_panel_layout(self) -> None:
        """Mantiene una vista de dos paneles amplia y una alternativa segura en vertical."""
        if not hasattr(self, "main_panels_layout"):
            return
        compact = self.width() < 1150
        self.main_panels_layout.addWidget(self.files_group, 0, 0)
        self.main_panels_layout.addWidget(self.configuration_group, 1 if compact else 0, 0 if compact else 1)
        self.main_panels_layout.setColumnStretch(0, 1)
        self.main_panels_layout.setColumnStretch(1, 0 if compact else 1)

    def _choose_files(self) -> None:
        if self.is_running:
            return
        folder = str(self._settings.value("paths/input", ""))
        names, _ = QFileDialog.getOpenFileNames(self, "Selecciona archivos Excel", folder, "Archivos Excel (*.xlsx *.xlsm)")
        if names:
            self._settings.setValue("paths/input", str(Path(names[0]).parent))
        self.file_list.add_files([Path(name) for name in names])

    def _choose_output(self) -> None:
        if self.is_running:
            return
        suggested = self.output_edit.text() or str(Path(str(self._settings.value("paths/output", ""))) / "control_tempo.xlsx")
        name, _ = QFileDialog.getSaveFileName(self, "Guardar Control Tempo como", suggested, "Excel (*.xlsx)")
        if name:
            path = Path(name)
            path = path if path.suffix.lower() == ".xlsx" else path.with_suffix(".xlsx")
            self.output_edit.setText(str(path))
            self._settings.setValue("paths/output", str(path.parent))

    def _on_files_changed(self, _files: list[Path]) -> None:
        self._update_form_state()

    def _restore_last_input_files(self) -> None:
        saved_paths = self._settings.value("control_tempo/last_successful_input_files", [])
        if isinstance(saved_paths, str):
            saved_paths = [saved_paths]
        if isinstance(saved_paths, (list, tuple)):
            self.file_list.restore_files([Path(value) for value in saved_paths if value])

    def _persist_successful_input_files(self) -> None:
        self._settings.setValue(
            "control_tempo/last_successful_input_files",
            [str(path) for path in self.file_list.files],
        )

    def _selected_date(self) -> date:
        return self.date_edit.date().toPython()

    def _selected_process(self) -> str:
        return PROCESS_MODE_MONTHLY if self.monthly_radio.isChecked() else PROCESS_MODE_DAILY

    def _update_period_description(self) -> None:
        selected = self._selected_date()
        if self._selected_process() == PROCESS_MODE_DAILY:
            text = f"Se tomarán los datos correspondientes al {selected:%d/%m/%Y}."
        elif selected.day >= 21:
            next_month = 1 if selected.month == 12 else selected.month + 1
            text = f"Periodo 20–20: del 21/{selected:%m/%Y} al {selected:%d/%m/%Y}. Se usará el bloque {MONTHS[next_month - 1]}."
        else:
            previous_month_end = selected.replace(day=1) - timedelta(days=1)
            text = f"Periodo 20–20: del 21/{previous_month_end:%m/%Y} al {selected:%d/%m/%Y}. Se usará el bloque {MONTHS[selected.month - 1]}."
        self.period_label.setText(text)
        self._update_form_state()

    def _normalise_output_path(self) -> Path | None:
        raw = self.output_edit.text().strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        return path if path.suffix.lower() == ".xlsx" else path.with_suffix(".xlsx")

    def _update_form_state(self) -> None:
        if self.is_running:
            return
        output = self._normalise_output_path()
        missing_files = [path for path in self.file_list.files if not path.is_file()]
        ready = bool(self.file_list.files and output and not missing_files)
        self.generate_button.setEnabled(ready)
        if not self.file_list.files:
            self.summary.setText("Añade uno o varios partes Excel para continuar.")
            idle_status = "Añade partes y define la salida para comenzar."
        elif missing_files:
            self.summary.setText(f"Hay {len(missing_files)} ruta(s) de entrada no disponible(s). Revisa la red o quítalas de la lista.")
            idle_status = "No se puede iniciar hasta que todos los archivos de entrada estén disponibles."
        elif not output:
            self.summary.setText("Elige el archivo Excel de salida.")
            idle_status = "La salida todavía no está definida."
        else:
            self.summary.setText(f"Listo · {len(self.file_list.files)} parte(s) · {self._selected_date():%d/%m/%Y} · {'Mensual 20–20' if self.monthly_radio.isChecked() else 'Diario'}.")
            idle_status = "Configuración completa. Ya puedes generar Control Tempo."
        if not self._details:
            self._set_activity_state("Listo para ejecutar" if ready else "Preparación pendiente", "activityReady" if ready else "activityPending")
            self.activity_metrics_label.setText(f"Partes seleccionados: {len(self.file_list.files)}")
            self.elapsed_label.setText("Tiempo transcurrido: —")
            self.progress.setFormat("Sin ejecución")
            self._set_status(idle_status, "statusInfo")

    def _set_activity_state(self, text: str, style_name: str) -> None:
        self.activity_state_label.setObjectName(style_name)
        self.activity_state_label.setText(text)
        self.activity_state_label.setAccessibleDescription(text)
        self.activity_state_label.style().unpolish(self.activity_state_label)
        self.activity_state_label.style().polish(self.activity_state_label)

    @staticmethod
    def _format_elapsed(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"

    def _start_activity_timer(self) -> None:
        self._elapsed_timer.start()
        self._activity_timer.start()
        self._update_elapsed_time()

    def _stop_activity_timer(self) -> None:
        if self._elapsed_timer.isValid():
            self._update_elapsed_time()
        self._activity_timer.stop()

    def _update_elapsed_time(self) -> None:
        if self._elapsed_timer.isValid():
            self.elapsed_label.setText(f"Tiempo transcurrido: {self._format_elapsed(self._elapsed_timer.elapsed())}")

    def _update_activity_metrics(self) -> None:
        if self._total_files:
            self.activity_metrics_label.setText(f"Archivos procesados: {self._completed_files}/{self._total_files}")

    def _build_request(self) -> ProcessRequest | None:
        output = self._normalise_output_path()
        if output is None:
            QMessageBox.warning(self, "Falta salida", "Elige el nombre y la ubicación del Excel final.")
            return None
        if not self.file_list.files:
            QMessageBox.warning(self, "Faltan archivos", "Añade al menos un archivo Excel de entrada.")
            return None
        input_paths = {path.resolve() for path in self.file_list.files if path.exists()}
        try:
            same_as_input = output.resolve() in input_paths
        except OSError:
            same_as_input = False
        if same_as_input:
            QMessageBox.warning(self, "Salida no válida", "El Excel de salida no puede ser uno de los archivos de entrada.")
            return None
        if output.exists():
            answer = QMessageBox.question(self, "Confirmar sobrescritura", f"El archivo ya existe y se sustituirá:\n\n{output}\n\n¿Deseas continuar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return None
        selected = datetime.combine(self._selected_date(), time.min)
        return ProcessRequest(tuple(self.file_list.files), selected, output, EMPLOYMENT_MODE_ACTIVE, self._selected_process())

    def _start_processing(self) -> None:
        if self.is_running:
            return
        request = self._build_request()
        if request is None:
            return
        self.output_edit.setText(str(request.output_path))
        self._details = [
            "RESUMEN INICIAL",
            f"Archivos seleccionados: {len(request.input_files)}",
            f"Fecha de consulta: {request.selected_date:%d/%m/%Y}",
            f"Proceso: {request.process_mode}",
            f"Salida: {request.output_path}",
            "-" * 60,
        ]
        self._last_result = None
        self._completed_files = 0
        self._total_files = len(request.input_files)
        self.progress.setRange(0, max(len(request.input_files) * 9 + 1, 1))
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self._set_activity_state("En ejecución", "activityRunning")
        self._update_activity_metrics()
        self._set_status("Preparando Control Tempo…", "statusInfo")
        self._start_activity_timer()
        self.open_file_button.setVisible(False)
        self.open_folder_button.setVisible(False)
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = Fase1Worker(request)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        self.file_list.setEnabled(not running)
        self.back_button.setEnabled(not running)
        self.configuration_group.setEnabled(not running)
        self.generate_button.setEnabled(not running and bool(self.file_list.files and self._normalise_output_path()))
        self.reset_button.setEnabled(not running)
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)
        self.details_button.setEnabled(bool(self._details) and not running)
        for name, action in self._shortcut_actions.items():
            action.setEnabled(not running and (name != "details" or bool(self._details)))

    def _set_status(self, text: str, style_name: str) -> None:
        self.status_label.setObjectName(style_name)
        self.status_label.setText(text)
        self.status_label.setAccessibleDescription(text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_progress(self, update: ProgressUpdate) -> None:
        self._total_files = update.total_files or self._total_files
        if update.event == "file_completed":
            self._completed_files = update.completed_files
        self.progress.setRange(0, max(update.total_units, 1))
        self.progress.setValue(min(update.completed_units, update.total_units))
        status = self._friendly_status(update)
        self._set_status(status, "statusInfo")
        self._update_activity_metrics()
        detail = f"{update.file_name}: {update.message}" if update.file_name else update.message
        if detail:
            self._details.append(detail)

    def _friendly_status(self, update: ProgressUpdate) -> str:
        total = update.total_files or self._total_files
        current = min(self._completed_files + 1, total) if total else 0
        if update.event == "writing":
            return "Creando el Excel final de Control Tempo…"
        if update.event == "audit":
            return f"Comprobando resultados del Excel {current} de {total}…"
        if update.event == "file_completed":
            return f"Procesados {self._completed_files} de {total} archivos Excel."
        message = update.message.lower()
        if "limpi" in message:
            return f"Preparando datos del Excel {current} de {total}…"
        if "abriendo" in message or "leyendo" in message:
            return f"Leyendo el Excel {current} de {total}…"
        return f"Procesando Excel {current} de {total}."

    def _request_cancel(self) -> None:
        if self._worker is None:
            return
        self._worker.request_cancel()
        self.cancel_button.setEnabled(False)
        self._set_activity_state("Cancelación solicitada", "activityWarning")
        self._set_status("Cancelación solicitada. Se detendrá al terminar la operación segura actual.", "statusWarning")
        self._details.append("Cancelación solicitada por el usuario.")

    def _on_finished(self, result: ProcessResult) -> None:
        self._last_result = result
        self._persist_successful_input_files()
        self._details.extend(result.detail_lines)
        self.progress.setValue(self.progress.maximum())
        self.progress.setFormat("100%")
        self._completed_files = len(result.audits)
        self._total_files = len(result.audits)
        self._update_activity_metrics()
        self.activity_metrics_label.setText(f"Archivos procesados: {len(result.audits)} · Trabajadores exportados: {result.worker_count}")
        self._stop_activity_timer()
        self._set_activity_state("Completado", "activitySuccess")
        self._set_status(f"Proceso finalizado correctamente. Trabajadores exportados: {result.worker_count}.", "statusSuccess")
        self.open_file_button.setVisible(True)
        self.open_folder_button.setVisible(True)

    def _on_failed(self, message: str, detail: str) -> None:
        self._details.append("ERROR:\n" + detail)
        self._stop_activity_timer()
        self._set_activity_state("Requiere atención", "activityWarning")
        self._set_status("No se pudo completar el proceso. Revisa el mensaje y los detalles técnicos.", "statusWarning")
        ErrorDialog(message, detail, self).exec()

    def _on_cancelled(self) -> None:
        self._details.append("Proceso cancelado sin generar una salida final.")
        self._stop_activity_timer()
        self._set_activity_state("Cancelado", "activityWarning")
        self._set_status("Proceso cancelado. No se ha generado una salida final.", "statusWarning")

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_running(False)
        self.details_button.setEnabled(bool(self._details))

    def show_context_help(self) -> None:
        output = self._normalise_output_path()
        process = "Mensual 20–20" if self.monthly_radio.isChecked() else "Diario"
        QMessageBox.information(
            self,
            "Ayuda de Control Tempo",
            "1. Añade uno o varios partes Excel.\n"
            "2. Revisa fecha y proceso.\n"
            "3. Indica el archivo de salida.\n"
            "4. Genera el Control Tempo.\n\n"
            f"Estado actual:\n"
            f"• Archivos: {len(self.file_list.files)}\n"
            f"• Fecha: {self._selected_date():%d/%m/%Y}\n"
            f"• Proceso: {process}\n"
            f"• Salida: {output or 'sin definir'}\n\n"
            f"{self.period_label.text()}",
        )

    def _show_details(self) -> None:
        DetailsDialog(self._details or ["Aún no hay detalles de ejecución de Control Tempo."], self).exec()

    def _reset_form(self) -> None:
        if self.file_list.files or self.output_edit.text().strip() or self._details:
            answer = QMessageBox.question(self, "Restablecer formulario", "Se eliminarán los archivos, la salida y los detalles actuales. ¿Deseas continuar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.file_list.clear()
        self.output_edit.clear()
        self.date_edit.setDate(QDate.currentDate())
        self.daily_radio.setChecked(True)
        self._details.clear()
        self._last_result = None
        self.progress.setValue(0)
        self._stop_activity_timer()
        self.details_button.setEnabled(False)
        self.open_file_button.setVisible(False)
        self.open_folder_button.setVisible(False)
        self._update_form_state()

    def _open_output_file(self) -> None:
        if self._last_result and self._last_result.output_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path)))

    def _open_output_folder(self) -> None:
        path = self._normalise_output_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def request_leave(self) -> bool:
        if not self.is_running:
            return True
        answer = QMessageBox.question(self, "Control Tempo en curso", "Hay un Control Tempo en curso. Puedes solicitar su cancelación y volver cuando termine. ¿Solicitar cancelación?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._request_cancel()
        return False
