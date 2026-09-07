"""Página PySide6 del Comparador de Tempo."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QProcess, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QBoxLayout, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QProgressBar,
    QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import ComparatorIncident, ComparatorRequest, ComparatorResult, ComparatorRow, ProgressUpdate
from services.comparador_tempo_service import RESULT_COLUMNS, TIME_COLUMNS
from ui.dialogs.comparador_tempo_help_dialog import ComparadorTempoHelpDialog
from ui.dialogs.details_dialog import DetailsDialog
from ui.dialogs.error_dialog import ErrorDialog


class ComparadorTempoPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._process: QProcess | None = None
        self._run_directory: Path | None = None
        self._events_file: Path | None = None
        self._result_file: Path | None = None
        self._cancel_file: Path | None = None
        self._event_offset = 0
        self._runner_failure: tuple[str, str] | None = None
        self._runner_cancelled = False
        self._last_result: ComparatorResult | None = None
        self._details: list[str] = []
        self._timer = QElapsedTimer()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(150)
        self._poll_timer.timeout.connect(self._poll_events)
        self._shortcuts: dict[str, QAction] = {}
        self._build_ui()
        self._install_shortcuts()
        self._update_state()

    @property
    def is_running(self) -> bool:
        return self._process is not None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        self.back_button = QPushButton("← Inicio")
        self.back_button.setAccessibleName("Volver a Inicio")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button, 0, Qt.AlignLeft)
        heading = QVBoxLayout()
        title = QLabel("Comparador de Tempo")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        self.subtitle_label = QLabel("Contrasta el Excel de Acumulado y el Excel Tempo SAP por código de trabajador, manteniendo el periodo elegido.")
        self.subtitle_label.setObjectName("mutedLabel")
        self.subtitle_label.setWordWrap(True)
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)
        self.header_status_label = QLabel("Preparación")
        self.header_status_label.setObjectName("modeBadge")
        header.addWidget(self.header_status_label, 0, Qt.AlignRight)
        self.new_comparison_button = QPushButton("Nueva comprobación")
        self.new_comparison_button.setToolTip("Limpiar la selección y comenzar otra comprobación")
        self.new_comparison_button.clicked.connect(self._clear)
        self.new_comparison_button.setVisible(False)
        header.addWidget(self.new_comparison_button, 0, Qt.AlignRight)
        outer.addLayout(header)

        self.state_stack = QStackedWidget()
        self.state_stack.setObjectName("comparisonStateStack")
        self.preparation_state = self._build_preparation_state()
        self.processing_state = self._build_processing_state()
        self.result_state = self._build_result_state()
        self.state_stack.addWidget(self.preparation_state)
        self.state_stack.addWidget(self.processing_state)
        self.state_stack.addWidget(self.result_state)
        outer.addWidget(self.state_stack, 1)
        self._show_view("preparation")

    def _build_preparation_state(self) -> QWidget:
        state = QWidget()
        layout = QVBoxLayout(state)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.inputs_group = QFrame()
        self.inputs_group.setObjectName("comparisonSetupCard")
        self.inputs_group.setMinimumHeight(510)
        self.inputs_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card = QVBoxLayout(self.inputs_group)
        card.setContentsMargins(30, 28, 30, 24)
        card.setSpacing(14)

        self.preparation_body = QHBoxLayout()
        self.preparation_body.setSpacing(20)
        intro_panel = QFrame()
        intro_panel.setObjectName("preparationIntroPanel")
        intro = QVBoxLayout(intro_panel)
        intro.setContentsMargins(24, 22, 24, 22)
        intro.setSpacing(12)

        title = QLabel("Prepara la comparación")
        title.setObjectName("stateTitle")
        intro.addWidget(title)
        helper = QLabel("Selecciona los dos archivos. Al comprobarlos, la vista previa mostrará únicamente los trabajadores que necesitan revisión.")
        helper.setObjectName("stateSubtitle")
        helper.setWordWrap(True)
        intro.addWidget(helper)
        intro.addSpacing(8)

        steps = QVBoxLayout()
        steps.setSpacing(8)
        self.preparation_steps: list[QLabel] = []
        for number, text in (("1", "Selecciona acumulado"), ("2", "Añade Tempo SAP"), ("3", "Comprueba datos")):
            step = QLabel(f"{number}  {text}")
            step.setObjectName("comparisonStep")
            step.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.preparation_steps.append(step)
            steps.addWidget(step)
        intro.addLayout(steps)
        intro.addStretch(1)
        outcome = QLabel("Se generarán un Excel de revisión y otro de incidencias. Los archivos de origen no se modifican.")
        outcome.setObjectName("preparationOutcome")
        outcome.setWordWrap(True)
        intro.addWidget(outcome)
        summary = QFrame()
        summary.setObjectName("comparisonSummaryCard")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(5)
        summary_title = QLabel("Qué verás en el resultado")
        summary_title.setObjectName("summaryCardTitle")
        summary_layout.addWidget(summary_title)
        summary_text = QLabel(
            "• Se muestran solo los trabajadores que requieren revisión.\n"
            "• Cada columna Δ calcula: tiempo SAP − tiempo del Acumulado.\n"
            "• ABSENT muestra SAP 1052-HDESC − Acumulado cuando existe absentismo; los controles SAP directos se resaltan en rojo."
        )
        summary_text.setObjectName("summaryCardText")
        summary_text.setWordWrap(True)
        summary_layout.addWidget(summary_text)
        intro.addWidget(summary)
        self.preparation_body.addWidget(intro_panel, 3)

        source_panel = QFrame()
        source_panel.setObjectName("sourceSelectionPanel")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(22, 20, 22, 20)
        source_layout.setSpacing(12)
        source_title = QLabel("Archivos a comparar")
        source_title.setObjectName("sourceCardTitle")
        source_layout.addWidget(source_title)
        source_hint = QLabel("Selecciona ambos archivos para habilitar la comprobación.")
        source_hint.setObjectName("mutedLabel")
        source_layout.addWidget(source_hint)
        self.tempo_edit = QLineEdit(self.inputs_group)
        self.tempo_edit.setAccessibleName("Ruta del Excel de Acumulado")
        self.tempo_edit.setVisible(False)
        self.tempo_edit.textChanged.connect(self._update_state)
        self.sap_edit = QLineEdit(self.inputs_group)
        self.sap_edit.setAccessibleName("Ruta del Excel Tempo SAP")
        self.sap_edit.setVisible(False)
        self.sap_edit.textChanged.connect(self._update_state)
        tempo_card, self.tempo_file_name, self.tempo_file_location, self.tempo_file_status, self.tempo_button = self._source_selector_card("Excel de Acumulado", "Tabla dinámica con el periodo seleccionado", self._choose_tempo)
        sap_card, self.sap_file_name, self.sap_file_location, self.sap_file_status, self.sap_button = self._source_selector_card("Excel Tempo SAP", "Exportación SAP de tiempos por trabajador (.xls o .xlsx)", self._choose_sap)
        source_layout.addWidget(tempo_card)
        source_layout.addWidget(sap_card)
        self.preparation_body.addWidget(source_panel, 4)
        card.addLayout(self.preparation_body)

        self.inputs_helper = QLabel("Los filtros de fecha existentes en el Acumulado se respetan. La comparación se realiza por código SAP y los archivos originales no se modifican.")
        self.inputs_helper.setObjectName("mutedLabel")
        self.inputs_helper.setWordWrap(True)
        self.inputs_helper.setAlignment(Qt.AlignLeft)
        card.addWidget(self.inputs_helper)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.compare_button = QPushButton("Comprobar datos")
        self.compare_button.setObjectName("primaryButton")
        self.compare_button.setAccessibleName("Comprobar datos de Tempo y SAP")
        self.compare_button.clicked.connect(self._start)
        self.clear_button = QPushButton("Limpiar")
        self.clear_button.setAccessibleName("Limpiar archivos y resultados del Comparador de Tempo")
        self.clear_button.setToolTip("Restablecer la pantalla inicial y eliminar la selección actual.")
        self.clear_button.clicked.connect(self._clear)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setVisible(False)
        self.details_button = QPushButton("Detalles")
        self.details_button.clicked.connect(self._show_details)
        self.details_button.setEnabled(False)
        controls.addWidget(self.compare_button)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        card.addLayout(controls)
        self.preparation_status_label = QLabel("Selecciona los dos archivos de origen para empezar.")
        self.preparation_status_label.setObjectName("mutedLabel")
        self.preparation_status_label.setAlignment(Qt.AlignHCenter)
        self.preparation_status_label.setWordWrap(True)
        card.addWidget(self.preparation_status_label)
        layout.addWidget(self.inputs_group)
        layout.addStretch(1)
        return state

    def _source_selector_card(self, title: str, description: str, callback):
        card = QFrame()
        card.setObjectName("sourceSelectorCard")
        card.setMinimumHeight(142)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(13)
        badge = QLabel("XLS")
        badge.setObjectName("fileTypeBadge")
        card_layout.addWidget(badge, 0, Qt.AlignTop)
        content = QVBoxLayout()
        content.setSpacing(3)
        heading = QLabel(title)
        heading.setObjectName("sourceCardTitle")
        content.addWidget(heading)
        detail = QLabel(description)
        detail.setObjectName("mutedLabel")
        detail.setWordWrap(True)
        content.addWidget(detail)
        filename = QLabel("Aún no seleccionado")
        filename.setObjectName("sourceFileName")
        filename.setWordWrap(True)
        content.addWidget(filename)
        location = QLabel("Elige un archivo Excel para continuar")
        location.setObjectName("sourceFileLocation")
        location.setWordWrap(True)
        content.addWidget(location)
        card_layout.addLayout(content, 1)
        footer = QVBoxLayout()
        footer.setSpacing(8)
        status = QLabel("Pendiente")
        status.setObjectName("fileStatusPending")
        footer.addWidget(status, 0, Qt.AlignRight)
        footer.addStretch(1)
        button = QPushButton("Seleccionar archivo…")
        button.setAccessibleName(f"Seleccionar {title}")
        button.clicked.connect(callback)
        footer.addWidget(button)
        card_layout.addLayout(footer)
        return card, filename, location, status, button

    def _build_processing_state(self) -> QWidget:
        state = QWidget()
        layout = QVBoxLayout(state)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.processing_panel = QFrame()
        self.processing_panel.setObjectName("comparisonProgressCard")
        self.processing_panel.setMinimumHeight(430)
        self.processing_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        card = QVBoxLayout(self.processing_panel)
        card.setContentsMargins(30, 26, 30, 24)
        card.setSpacing(12)
        title_row = QHBoxLayout()
        title = QLabel("Comprobando datos…")
        title.setObjectName("stateTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.elapsed_label = QLabel("Tiempo transcurrido: 00:00")
        self.elapsed_label.setObjectName("processingElapsed")
        title_row.addWidget(self.elapsed_label)
        card.addLayout(title_row)
        self.processing_status_label = QLabel("Preparando comparación aislada…")
        self.processing_status_label.setObjectName("statusInfo")
        self.processing_status_label.setWordWrap(True)
        card.addWidget(self.processing_status_label)
        self.processing_sources_label = QLabel()
        self.processing_sources_label.setObjectName("processingSourceStrip")
        self.processing_sources_label.setWordWrap(True)
        card.addWidget(self.processing_sources_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 8)
        self.progress.setValue(0)
        self.progress.setAccessibleName("Progreso de la comparación")
        card.addWidget(self.progress)
        progress_hint = QLabel("La comprobación se ejecuta en un proceso aislado: la aplicación seguirá respondiendo mientras se procesan los dos Excel.")
        progress_hint.setObjectName("mutedLabel")
        progress_hint.setWordWrap(True)
        card.addWidget(progress_hint)

        steps_panel = QFrame()
        steps_panel.setObjectName("processingStepsPanel")
        self.processing_steps_layout = QHBoxLayout(steps_panel)
        self.processing_steps_layout.setContentsMargins(18, 14, 18, 14)
        self.processing_steps_layout.setSpacing(28)
        left_steps = QVBoxLayout()
        right_steps = QVBoxLayout()
        left_steps.setSpacing(5)
        right_steps.setSpacing(5)
        self.processing_steps_layout.addLayout(left_steps, 1)
        self.processing_steps_layout.addLayout(right_steps, 1)
        self.processing_steps: list[tuple[int, QLabel, QLabel]] = []
        for index, (threshold, text) in enumerate(((1, "Preparar relación de trabajadores"), (3, "Leer la tabla dinámica de Tempo"), (5, "Leer y normalizar el informe SAP"), (6, "Comparar acumulados e incidencias"), (8, "Generar los dos Excel de salida"))):
            row = QHBoxLayout()
            label = QLabel(text)
            label.setObjectName("processingStep")
            marker = QLabel("Pendiente")
            marker.setObjectName("processingStepPending")
            row.addWidget(label, 1)
            row.addWidget(marker)
            (left_steps if index < 3 else right_steps).addLayout(row)
            self.processing_steps.append((threshold, label, marker))
        card.addWidget(steps_panel)
        card.addSpacing(4)
        cancel_row = QHBoxLayout()
        cancel_row.addWidget(QLabel("Puedes cancelar; se conservarán los archivos originales."), 1)
        cancel_row.addWidget(self.cancel_button)
        card.addLayout(cancel_row)
        layout.addWidget(self.processing_panel)
        layout.addStretch(1)
        return state

    def _build_result_state(self) -> QWidget:
        state = QWidget()
        layout = QVBoxLayout(state)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.result_context_bar = QFrame()
        self.result_context_bar.setObjectName("sourceContextBar")
        context = QHBoxLayout(self.result_context_bar)
        context.setContentsMargins(16, 10, 16, 10)
        context.setSpacing(14)
        label = QLabel("Archivos comprobados")
        label.setObjectName("contextTitle")
        context.addWidget(label)
        self.result_tempo_chip = QLabel()
        self.result_tempo_chip.setObjectName("fileContextChip")
        context.addWidget(self.result_tempo_chip, 1)
        self.result_sap_chip = QLabel()
        self.result_sap_chip.setObjectName("fileContextChip")
        context.addWidget(self.result_sap_chip, 1)
        self.workers_value_label = QLabel("0 trabajadores")
        self.workers_value_label.setObjectName("contextMetric")
        context.addWidget(self.workers_value_label)
        self.incidents_value_label = QLabel("0 incidencias")
        self.incidents_value_label.setObjectName("contextMetric")
        context.addWidget(self.incidents_value_label)
        self.result_summary_label = QLabel("Aún sin resultados")
        self.result_summary_label.setObjectName("mutedLabel")
        context.addWidget(self.result_summary_label)
        change_button = QPushButton("Cambiar archivos")
        change_button.setToolTip("Volver a la selección de archivos conservando los actuales")
        change_button.clicked.connect(self._return_to_preparation)
        context.addWidget(change_button)
        layout.addWidget(self.result_context_bar)

        self.preview_group = QFrame()
        self.preview_group.setObjectName("resultPreviewCard")
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(16, 14, 16, 12)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_title = QLabel("Vista previa del resultado")
        preview_title.setObjectName("sectionLabel")
        preview_header.addWidget(preview_title)
        preview_header.addSpacing(12)
        preview_header.addWidget(QLabel("Sección"))
        self.section_filter = QComboBox()
        self.section_filter.setAccessibleName("Filtrar vista previa por sección")
        self.section_filter.currentTextChanged.connect(self._refresh_preview)
        preview_header.addWidget(self.section_filter)
        self.worker_search = QLineEdit()
        self.worker_search.setPlaceholderText("Buscar trabajador o incidencia…")
        self.worker_search.setAccessibleName("Filtrar trabajadores e incidencias")
        self.worker_search.setClearButtonEnabled(True)
        self.worker_search.textChanged.connect(self._refresh_preview)
        self.worker_search.setMinimumWidth(260)
        preview_header.addWidget(self.worker_search)
        preview_header.addStretch(1)
        self.preview_count = QLabel("Sin resultados")
        self.preview_count.setObjectName("mutedLabel")
        preview_header.addWidget(self.preview_count)
        preview_layout.addLayout(preview_header)
        self.preview_table = QTableWidget(0, len(RESULT_COLUMNS))
        self.preview_table.setHorizontalHeaderLabels(RESULT_COLUMNS)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.preview_table.setAccessibleName("Vista previa de trabajadores a revisar")
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setMinimumHeight(210)
        self.preview_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout.addWidget(self.preview_table, 1)
        actions = QHBoxLayout()
        self.open_result_button = QPushButton("Abrir resultado")
        self.open_result_button.clicked.connect(self._open_result)
        self.open_incidents_button = QPushButton("Abrir incidencias")
        self.open_incidents_button.clicked.connect(self._open_incidents)
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self._open_folder)
        for button in (self.open_result_button, self.open_incidents_button, self.open_folder_button):
            button.setVisible(False)
            actions.addWidget(button)
        actions.addWidget(self.details_button)
        actions.addStretch(1)
        preview_layout.addLayout(actions)
        layout.addWidget(self.preview_group, 1)
        return state

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Evita que las tarjetas se estrechen cuando una ventana deja de ser ancha."""
        narrow = self.width() < 1120
        direction = QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        self.preparation_body.setDirection(direction)
        self.processing_steps_layout.setDirection(direction)

    def _show_view(self, view: str) -> None:
        mapping = {"preparation": self.preparation_state, "processing": self.processing_state, "result": self.result_state}
        widget = mapping[view]
        self.state_stack.setCurrentWidget(widget)
        self.header_status_label.setText({"preparation": "PREPARACIÓN", "processing": "COMPARANDO", "result": "RESULTADO"}[view])
        self.new_comparison_button.setVisible(view == "result")
        self.subtitle_label.setVisible(view == "preparation")

    def _return_to_preparation(self) -> None:
        if not self.is_running:
            self._show_view("preparation")
            self._update_state()

    @staticmethod
    def _location_caption(path: Path) -> str:
        parents = list(path.parent.parts)
        return " · ".join(parents[-2:]) if len(parents) >= 2 else str(path.parent)

    def _update_source_presentation(self) -> None:
        for edit, filename, location, status, prefix in (
            (self.tempo_edit, self.tempo_file_name, self.tempo_file_location, self.tempo_file_status, "Tempo"),
            (self.sap_edit, self.sap_file_name, self.sap_file_location, self.sap_file_status, "SAP"),
        ):
            raw = edit.text().strip()
            if raw:
                path = Path(raw)
                filename.setText(path.name)
                filename.setToolTip(raw)
                location.setText(self._location_caption(path))
                location.setToolTip(raw)
                status.setText("Seleccionado")
                status.setObjectName("fileStatusReady")
            else:
                filename.setText("Aún no seleccionado")
                filename.setToolTip("")
                location.setText("Elige un archivo Excel para continuar")
                location.setToolTip("")
                status.setText("Pendiente")
                status.setObjectName("fileStatusPending")
            status.style().unpolish(status)
            status.style().polish(status)
        tempo_name = Path(self.tempo_edit.text()).name if self.tempo_edit.text().strip() else "Tempo pendiente"
        sap_name = Path(self.sap_edit.text()).name if self.sap_edit.text().strip() else "SAP pendiente"
        self.processing_sources_label.setText(f"Acumulado: {tempo_name}    ·    Tempo SAP: {sap_name}")
        self.result_tempo_chip.setText(f"Acumulado · {tempo_name}")
        self.result_sap_chip.setText(f"Tempo SAP · {sap_name}")

    def _reset_result_presentation(self) -> None:
        self._last_result = None
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.blockSignals(False)
        self.worker_search.clear()
        self.preview_table.clearContents()
        self.preview_table.setRowCount(0)
        self.preview_count.setText("Sin resultados")
        self.workers_value_label.setText("0 trabajadores")
        self.incidents_value_label.setText("0 incidencias")
        self.result_summary_label.setText("Aún sin resultados")
        for button in (self.open_result_button, self.open_incidents_button, self.open_folder_button):
            button.setVisible(False)

    def _clear(self) -> None:
        if self.is_running:
            return
        self.tempo_edit.clear()
        self.sap_edit.clear()
        self._details.clear()
        self._reset_result_presentation()
        self.progress.setRange(0, 8)
        self.progress.setValue(0)
        self.elapsed_label.setText("Sin ejecución activa")
        self.details_button.setEnabled(False)
        self._set_status("Selecciona los dos archivos de origen para empezar.", "statusInfo")
        self._show_view("preparation")
        self.tempo_button.setFocus()

    def _install_shortcuts(self) -> None:
        for name, shortcut, callback in (("tempo", "Ctrl+O", self._choose_tempo), ("run", "Ctrl+R", self._start), ("details", "Ctrl+D", self._show_details)):
            action = QAction(self)
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self._shortcuts[name] = action

    def _choose_tempo(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Seleccionar Excel de Acumulado", self.tempo_edit.text(), "Excel (*.xlsx *.xlsm)")
        if chosen:
            self.tempo_edit.setText(chosen)

    def _choose_sap(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Excel Tempo SAP",
            self.sap_edit.text(),
            "Excel Tempo SAP (*.xlsx *.xlsm *.xls *.xml)",
        )
        if chosen:
            self.sap_edit.setText(chosen)

    def _choose_output(self) -> Path | None:
        default = Path.home() / "Documents" / f"Comparador_Tempo_{datetime.now():%Y%m%d}.xlsx"
        chosen, _ = QFileDialog.getSaveFileName(self, "Guardar resultado de comparación", str(default), "Excel (*.xlsx)")
        if not chosen:
            return None
        path = Path(chosen)
        return path if path.suffix.lower() == ".xlsx" else path.with_suffix(".xlsx")

    def _start(self) -> None:
        if self.is_running:
            return
        tempo, sap = Path(self.tempo_edit.text().strip()), Path(self.sap_edit.text().strip())
        if not tempo.is_file() or not sap.is_file():
            QMessageBox.warning(self, "Archivos pendientes", "Selecciona un Excel de Acumulado y un Excel Tempo SAP disponibles.")
            return
        output = self._choose_output()
        if output is None:
            return
        if output.exists():
            answer = QMessageBox.question(self, "Confirmar sustitución", f"Se sustituirá el resultado existente:\n\n{output}\n\n¿Deseas continuar?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        request = ComparatorRequest(tempo, sap, output)
        self._reset_result_presentation()
        self._details = [f"Acumulado: {tempo}", f"Tempo SAP: {sap}", f"Salida: {output}", "-" * 48]
        self.progress.setRange(0, 8)
        self.progress.setValue(0)
        self._reset_processing_steps()
        self._set_status("Preparando comparación aislada…", "statusInfo")
        self._set_running(True)
        self._timer.start()
        self._elapsed_timer.start()
        try:
            self._start_runner(request)
        except Exception as exc:
            self._runner_failure = (str(exc), traceback.format_exc())
            self._finish_runner()

    def _start_runner(self, request: ComparatorRequest) -> None:
        run_root = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Suite RRHH" / "runs"
        self._run_directory = run_root / f"comparador_tempo_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        self._run_directory.mkdir(parents=True, exist_ok=False)
        request_file = self._run_directory / "request.json"
        self._events_file = self._run_directory / "events.jsonl"
        self._result_file = self._run_directory / "result.json"
        self._cancel_file = self._run_directory / "cancel.requested"
        self._event_offset = 0
        self._runner_failure = None
        self._runner_cancelled = False
        request_file.write_text(json.dumps({"tempo_path": str(request.tempo_path), "sap_path": str(request.sap_path), "output_path": str(request.output_path)}, ensure_ascii=False), encoding="utf-8")
        runner = Path(__file__).resolve().parents[2] / "workers" / "comparador_tempo_runner.py"
        if not runner.is_file() or not Path(sys.executable).is_file():
            raise RuntimeError("No se encontró el ejecutor aislado o el motor Python de Suite RRHH.")
        process = QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments([str(runner), "--request-file", str(request_file), "--result-file", str(self._result_file), "--events-file", str(self._events_file), "--cancel-file", str(self._cancel_file)])
        process.setWorkingDirectory(str(runner.parent.parent))
        process.finished.connect(self._runner_finished)
        process.errorOccurred.connect(self._runner_error)
        self._process = process
        self._poll_timer.start()
        process.start()

    def _poll_events(self) -> None:
        if self._events_file is None or not self._events_file.exists():
            return
        try:
            with self._events_file.open("r", encoding="utf-8") as handle:
                handle.seek(self._event_offset)
                lines = handle.readlines()
                self._event_offset = handle.tell()
        except OSError:
            return
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "progress":
                update = event.get("update", {})
                progress = ProgressUpdate(str(update.get("event", "")), str(update.get("message", "")), completed_units=int(update.get("completed_units", 0) or 0), total_units=int(update.get("total_units", 8) or 8), rows=int(update.get("rows", 0) or 0))
                self.progress.setRange(0, max(progress.total_units, 1))
                self.progress.setValue(min(progress.completed_units, progress.total_units))
                self._set_status(progress.message, "statusInfo")
                self._update_processing_steps(progress.completed_units, progress.total_units)
                self._details.append(progress.message)
            elif event.get("event") == "error":
                self._runner_failure = (str(event.get("message", "Error del proceso aislado.")), str(event.get("detail", "")))
            elif event.get("event") == "cancelled":
                self._runner_cancelled = True

    def _runner_error(self, error) -> None:
        if self._process is not None and error == QProcess.ProcessError.FailedToStart:
            self._runner_failure = ("No se pudo iniciar el proceso aislado del Comparador de Tempo.", self._process.errorString())
            QTimer.singleShot(0, self._finish_runner)

    def _runner_finished(self, exit_code: int, exit_status) -> None:
        self._poll_events()
        if exit_status == QProcess.CrashExit and self._runner_failure is None:
            self._runner_failure = ("El proceso de comparación se cerró inesperadamente.", f"Código de salida: {exit_code}. Registro técnico: {self._run_directory}")
        self._finish_runner()

    def _finish_runner(self) -> None:
        self._poll_events()
        if self._process is not None:
            self._process.deleteLater()
        self._process = None
        self._poll_timer.stop()
        self._elapsed_timer.stop()
        self._set_running(False)
        payload = None
        if self._result_file and self._result_file.exists():
            try:
                payload = json.loads(self._result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._runner_failure = ("No se pudo leer el resultado del Comparador de Tempo.", str(exc))
        if payload and payload.get("state") == "success" and self._runner_failure is None:
            self._on_success(self._result_from_payload(payload["result"]))
        elif self._runner_cancelled or (payload and payload.get("state") == "cancelled"):
            self._set_status("Comparación cancelada sin generar resultados finales.", "statusWarning")
            self._details.append("Proceso cancelado por el usuario.")
        else:
            if payload and payload.get("state") == "failed":
                self._runner_failure = (str(payload.get("message", "Error en la comparación.")), str(payload.get("detail", "")))
            message, detail = self._runner_failure or ("El proceso aislado finalizó sin resultado.", f"Registro técnico: {self._run_directory}")
            self._set_status("No se pudo completar la comparación. Revisa los detalles técnicos.", "statusWarning")
            self._details.append("ERROR:\n" + detail)
            ErrorDialog(message, detail, self).exec()
        self.details_button.setEnabled(bool(self._details))

    @staticmethod
    def _result_from_payload(data: dict) -> ComparatorResult:
        rows = tuple(
            ComparatorRow(
                str(item["section"]),
                str(item["sap_code"]),
                str(item["worker"]),
                {str(k): int(v) for k, v in item.get("values_minutes", {}).items()},
                tuple(str(value) for value in item.get("trigger_fields", [])),
                tuple(str(value) for value in item.get("incidence_messages", [])),
                item.get("sap_daily_work_minutes"),
                tuple(str(value) for value in item.get("suppressed_fields", [])),
                item.get("sap_daily_minus_noise_minutes"),
                tuple(str(value) for value in item.get("red_fields", [])),
            )
            for item in data.get("rows", [])
        )
        incidents = tuple(ComparatorIncident(str(item["incident_type"]), str(item["section"]), str(item["sap_code"]), str(item["tempo_worker"]), str(item["sap_worker"]), str(item["field"]), item.get("tempo_minutes"), item.get("sap_minutes"), item.get("difference_minutes"), str(item["reason"]), {str(k): int(v) for k, v in item.get("tempo_values_minutes", {}).items()}, {str(k): int(v) for k, v in item.get("sap_values_minutes", {}).items()}) for item in data.get("incidents", []))
        return ComparatorResult(Path(data["output_path"]), Path(data["incidents_path"]), rows, incidents, tuple(str(value) for value in data.get("sections", [])), float(data.get("elapsed_seconds", 0)), tuple(str(value) for value in data.get("detail_lines", [])))

    def _on_success(self, result: ComparatorResult) -> None:
        self._last_result = result
        self._details.extend(result.detail_lines)
        self.progress.setValue(self.progress.maximum())
        self._set_status(f"Comparación terminada: {len(result.rows)} trabajadores para revisar y {len(result.incidents)} incidencias auditables.", "statusSuccess")
        self.workers_value_label.setText(f"{len(result.rows)} trabajadores")
        self.incidents_value_label.setText(f"{len(result.incidents)} incidencias")
        elapsed = int(result.elapsed_seconds)
        self.result_summary_label.setText(f"Completada · {elapsed // 60:02d}:{elapsed % 60:02d}")
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.addItem("Todas las secciones")
        self.section_filter.addItems(list(result.sections))
        self.section_filter.blockSignals(False)
        self._refresh_preview()
        for button in (self.open_result_button, self.open_incidents_button, self.open_folder_button):
            button.setVisible(True)
        self._show_view("result")
        self.section_filter.setFocus()

    def _refresh_preview(self) -> None:
        result = self._last_result
        if result is None:
            self.preview_table.setRowCount(0)
            self.preview_count.setText("Sin resultados")
            return
        selection = self.section_filter.currentText()
        rows = [row for row in result.rows if selection == "Todas las secciones" or row.section == selection]
        needle = self.worker_search.text().strip().casefold()
        if needle:
            rows = [
                row for row in rows
                if needle in row.worker.casefold()
                or needle in " ".join(row.incidence_messages).casefold()
                or needle in row.sap_code.casefold()
            ]
        self.preview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row.worker,
                "; ".join(row.incidence_messages) if row.incidence_messages else "-",
                self._format_minutes(row.sap_daily_work_minutes),
                self._format_difference(row.sap_daily_minus_noise_minutes or 0),
                *[
                    "-" if column in row.suppressed_fields else (
                        self._format_minutes(row.values_minutes.get(column, 0))
                        if column in row.red_fields else self._format_difference(row.values_minutes.get(column, 0))
                    )
                    for column in TIME_COLUMNS[:-1]
                ],
                self._format_difference(row.values_minutes.get("ABSENT", 0)) if "ABSENT" in row.red_fields else "-",
            ]
            red_columns = {
                4 + index
                for index, column in enumerate(TIME_COLUMNS[:-1])
                if column in row.red_fields
            }
            if "ABSENT" in row.red_fields:
                red_columns.add(len(values) - 1)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter if column in {0, 1} else Qt.AlignCenter)
                if column in red_columns:
                    item.setBackground(QColor("#FDE2E1"))
                    item.setForeground(QColor("#9C0006"))
                self.preview_table.setItem(row_index, column, item)
        self.preview_table.resizeColumnsToContents()
        self.preview_count.setText(f"{len(rows)} trabajador(es)")

    @staticmethod
    def _format_minutes(minutes: int | None) -> str:
        minutes = minutes or 0
        sign = "-" if minutes < 0 else ""
        value = abs(minutes)
        return f"{sign}{value // 60}:{value % 60:02d}"

    @staticmethod
    def _format_difference(minutes: int) -> str:
        sign = "+" if minutes > 0 else "-" if minutes < 0 else ""
        value = abs(minutes)
        return f"{sign}{value // 60}:{value % 60:02d}"

    def _cancel(self) -> None:
        if self._cancel_file is None:
            return
        try:
            self._cancel_file.touch(exist_ok=True)
        except OSError as exc:
            ErrorDialog("No se pudo solicitar la cancelación.", str(exc), self).exec()
            return
        self.cancel_button.setEnabled(False)
        self._set_status("Cancelación solicitada. Se detendrá al terminar la operación segura actual.", "statusWarning")

    def _set_running(self, running: bool) -> None:
        self.inputs_group.setEnabled(not running)
        self.back_button.setEnabled(not running)
        self.compare_button.setEnabled(not running and bool(self.tempo_edit.text().strip() and self.sap_edit.text().strip()))
        self.clear_button.setEnabled(not running)
        self.cancel_button.setVisible(running)
        self.cancel_button.setEnabled(running)
        self.section_filter.setEnabled(not running)
        self.worker_search.setEnabled(not running)
        for action in self._shortcuts.values():
            action.setEnabled(not running)
        if running:
            self._show_view("processing")
        elif self.state_stack.currentWidget() is self.processing_state:
            self._show_view("preparation")

    def _update_state(self) -> None:
        self._update_source_presentation()
        if not self.is_running:
            ready = bool(self.tempo_edit.text().strip() and self.sap_edit.text().strip())
            self.compare_button.setEnabled(ready)
            self.clear_button.setVisible(bool(self.tempo_edit.text().strip() or self.sap_edit.text().strip()))
            for index, step in enumerate(self.preparation_steps):
                complete = (index == 0 and bool(self.tempo_edit.text().strip())) or (index == 1 and bool(self.sap_edit.text().strip()))
                if index == 2:
                    complete = ready
                step.setObjectName("comparisonStepReady" if complete else "comparisonStep")
                step.style().unpolish(step)
                step.style().polish(step)

    def _set_status(self, text: str, name: str) -> None:
        for label in (self.processing_status_label, self.preparation_status_label):
            label.setObjectName(name)
            label.setText(text)
            label.setAccessibleDescription(text)
            label.style().unpolish(label)
            label.style().polish(label)

    def _reset_processing_steps(self) -> None:
        for _, label, marker in self.processing_steps:
            label.setObjectName("processingStep")
            marker.setText("Pendiente")
            marker.setObjectName("processingStepPending")
            for widget in (label, marker):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _update_processing_steps(self, completed: int, total: int) -> None:
        for threshold, label, marker in self.processing_steps:
            if completed >= threshold:
                label.setObjectName("processingStepDone")
                marker.setText("Completado")
                marker.setObjectName("processingStepDone")
            elif completed + 1 >= threshold:
                label.setObjectName("processingStepActive")
                marker.setText("En curso")
                marker.setObjectName("processingStepActive")
            else:
                label.setObjectName("processingStep")
                marker.setText("Pendiente")
                marker.setObjectName("processingStepPending")
            for widget in (label, marker):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def _update_elapsed(self) -> None:
        if self._timer.isValid():
            seconds = self._timer.elapsed() // 1000
            self.elapsed_label.setText(f"Tiempo transcurrido: {seconds // 60:02d}:{seconds % 60:02d}")

    def _show_details(self) -> None:
        DetailsDialog(self._details or ["Aún no hay detalles de comparación."], self).exec()

    def _open_result(self) -> None:
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path)))

    def _open_incidents(self) -> None:
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.incidents_path)))

    def _open_folder(self) -> None:
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path.parent)))

    def show_context_help(self) -> None:
        ComparadorTempoHelpDialog(self).exec()

    def request_leave(self) -> bool:
        if not self.is_running:
            return True
        answer = QMessageBox.question(self, "Comparación en curso", "Hay una comparación en curso. ¿Solicitar su cancelación?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._cancel()
        return False
