"""Página PySide6 del Comparador de Tempo."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QProcess, QSettings, QStandardPaths, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QBoxLayout, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QMenu, QToolButton,
    QLabel, QLineEdit, QMessageBox, QPushButton, QProgressBar, QProgressDialog,
    QSizePolicy, QSplitter, QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import ComparatorRequest, ComparatorResult, ComparatorRow, ProgressUpdate
from core.comparison_style import comparison_colors
from services.comparador_tempo_service import RESULT_COLUMNS, TIME_COLUMNS
from services.comparison_archive import load_archive, save_archive
from services.comparison_codec import result_from_payload
from workers.background_task import BackgroundTask
from ui.dialogs.comparador_tempo_help_dialog import ComparadorTempoHelpDialog
from ui.dialogs.details_dialog import DetailsDialog
from ui.dialogs.error_dialog import ErrorDialog
from ui.widgets.comparison_review import (
    ElidedLabel, FrozenIdentityTable, WorkerDetailPanel, calculation_text,
    matches_reason, matches_incidence, incidence_keys, review_order, search_key, duration, comparison_triplet,
)


class ComparadorTempoPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None, *, settings=None) -> None:
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings("Grupo Vall", "Suite RRHH")
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
        self._transfer_thread = None
        self._imported_archive = None
        self.setAcceptDrops(True)
        self._preview_rows: list[ComparatorRow] = []
        self._detail_dialog: QDialog | None = None
        self._dialog_detail_panel: WorkerDetailPanel | None = None
        self._detail_width = 560
        self._cell_cache = {}
        self._search_cache = {}
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(140)
        self._search_timer.timeout.connect(self._refresh_preview)
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
        self._set_review_tab_order()
        self._update_state()

    @property
    def is_running(self) -> bool:
        return self._process is not None or self._transfer_thread is not None

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(14)

        self.page_header = QWidget()
        header = QHBoxLayout(self.page_header)
        header.setContentsMargins(0, 0, 0, 0)
        self.back_button = QPushButton("← Inicio")
        self.back_button.setAccessibleName("Volver a Inicio")
        self.back_button.clicked.connect(self.back_requested.emit)
        header.addWidget(self.back_button, 0, Qt.AlignLeft)
        heading = QVBoxLayout()
        title = QLabel("Comparador de Tempo")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        self.subtitle_label = QLabel("Contrasta el Excel de Partes Mensuales y el Excel Tempo por código de trabajador, manteniendo el periodo elegido.")
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
        outer.addWidget(self.page_header)

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
        for number, text in (("1", "Selecciona Partes Mensuales"), ("2", "Añade Tempo"), ("3", "Comprueba datos")):
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
            "• Diferencias por sección y, al final, trabajadores que faltan en un origen.\n"
            "• Δ = Tempo − Partes Mensuales. Control = Trab. Real Tempo − RUIDO PM.\n"
            "• Ambos a cero: −. Tiempos iguales con datos: 0:00.\n"
            "• Verde: diferencia negativa. Amarillo: positiva. Rojo: control especial o absentismo.\n"
            "• Cada sección indica cuántos trabajadores se encuentran en cada origen."
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
        self.tempo_edit.setAccessibleName("Ruta del Excel de Partes Mensuales")
        self.tempo_edit.setVisible(False)
        self.tempo_edit.textChanged.connect(self._update_state)
        self.sap_edit = QLineEdit(self.inputs_group)
        self.sap_edit.setAccessibleName("Ruta del Excel Tempo")
        self.sap_edit.setVisible(False)
        self.sap_edit.textChanged.connect(self._update_state)
        tempo_card, self.tempo_file_name, self.tempo_file_location, self.tempo_file_status, self.tempo_button = self._source_selector_card("Excel de Partes Mensuales", "Tabla dinámica con el periodo seleccionado", self._choose_tempo)
        sap_card, self.sap_file_name, self.sap_file_location, self.sap_file_status, self.sap_button = self._source_selector_card("Excel Tempo", "Exportación Tempo de tiempos por trabajador (.xls o .xlsx)", self._choose_sap)
        source_layout.addWidget(tempo_card)
        source_layout.addWidget(sap_card)
        self.preparation_body.addWidget(source_panel, 4)
        card.addLayout(self.preparation_body)

        self.inputs_helper = QLabel("Los filtros de fecha existentes en Partes Mensuales se respetan. La comparación se realiza por código Tempo y los archivos originales no se modifican.")
        self.inputs_helper.setObjectName("mutedLabel")
        self.inputs_helper.setWordWrap(True)
        self.inputs_helper.setAlignment(Qt.AlignLeft)
        card.addWidget(self.inputs_helper)

        controls = QHBoxLayout()
        controls.addStretch(1)
        self.compare_button = QPushButton("Comprobar datos")
        self.compare_button.setObjectName("primaryButton")
        self.compare_button.setAccessibleName("Comprobar datos de Partes Mensuales y Tempo")
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
        self.import_button = QPushButton("Importar comparación…")
        self.import_button.setToolTip("Abre un archivo .rrhh recibido para consultar el resultado completo, sin los Excel originales.")
        self.import_button.clicked.connect(self._choose_import)
        controls.addWidget(self.import_button)
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
        for index, (threshold, text) in enumerate(((1, "Preparar relación de trabajadores"), (3, "Leer la tabla dinámica de Partes Mensuales"), (5, "Leer y normalizar el Excel Tempo"), (6, "Comparar Partes Mensuales e incidencias"), (8, "Generar los dos Excel de salida"))):
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
        label = QLabel("Origen")
        label.setObjectName("contextTitle")
        context.addWidget(label)
        self.result_tempo_chip = ElidedLabel()
        self.result_tempo_chip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.result_tempo_chip.setObjectName("fileContextChip")
        context.addWidget(self.result_tempo_chip, 1)
        self.result_sap_chip = ElidedLabel()
        self.result_sap_chip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.result_sap_chip.setObjectName("fileContextChip")
        context.addWidget(self.result_sap_chip, 1)
        self.paths_button = QPushButton("Ver rutas")
        self.paths_button.clicked.connect(self._show_source_paths)
        context.addWidget(self.paths_button)
        self.workers_value_label = QLabel("0 trabajadores")
        self.workers_value_label.setObjectName("contextMetric")
        self.incidents_value_label = QLabel("0 incidencias")
        self.incidents_value_label.setObjectName("contextMetric")
        self.result_summary_label = QLabel("Aún sin resultados")
        self.result_summary_label.setObjectName("mutedLabel")
        context.addWidget(self.result_summary_label)
        change_button = QPushButton("Cambiar archivos")
        change_button.setToolTip("Volver a la selección de archivos conservando los actuales")
        change_button.clicked.connect(self._return_to_preparation)
        context.addWidget(change_button)
        layout.addWidget(self.result_context_bar)
        self.result_context_bar.hide()

        self.preview_group = QFrame()
        self.preview_group.setObjectName("resultPreviewCard")
        preview_layout = QVBoxLayout(self.preview_group)
        preview_layout.setContentsMargins(10, 8, 10, 8)
        preview_layout.setSpacing(8)
        self.imported_label = QLabel()
        self.imported_label.setTextFormat(Qt.PlainText)
        self.imported_label.setObjectName("activeFilters")
        self.imported_label.setWordWrap(True)
        self.imported_label.hide()
        preview_layout.addWidget(self.imported_label)
        preview_header = QHBoxLayout()
        self.result_back_button = QPushButton("← Inicio")
        self.result_back_button.clicked.connect(self.back_requested.emit)
        preview_header.addWidget(self.result_back_button)
        preview_title = QLabel("Comparador de Tempo")
        preview_title.setObjectName("sectionLabel")
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(self.workers_value_label)
        preview_header.addWidget(self.incidents_value_label)
        self.view_options = QToolButton()
        self.view_options.setText("Vista")
        self.view_options.setObjectName("reviewViewOptions")
        self.view_options.setProperty("reviewMenuButton", True)
        self.view_options.setAccessibleName("Opciones de vista de la tabla")
        self.view_options.setPopupMode(QToolButton.InstantPopup)
        view_menu = QMenu(self.view_options)
        self.compact_action = view_menu.addAction("Filas compactas")
        self.compact_action.setCheckable(True)
        self.compact_action.setToolTip("Desactivado: filas cómodas. Activado: más trabajadores sin reducir la letra.")
        self.compact_action.toggled.connect(self._set_compact_view)
        self.accessible_action = view_menu.addAction("Lectura accesible · tabla única")
        self.accessible_action.setCheckable(True)
        self.accessible_action.setToolTip("Para lectores de pantalla: usa una sola tabla nativa, sin columnas congeladas duplicadas.")
        self.accessible_action.toggled.connect(self._set_accessible_view)
        view_menu.addSeparator()
        view_menu.addAction("Restablecer anchos", lambda: self.preview_table.reset_column_widths())
        self.view_options.setMenu(view_menu)
        self.sources_action = view_menu.addAction("Mostrar archivos de origen")
        self.sources_action.setCheckable(True)
        self.sources_action.toggled.connect(self.result_context_bar.setVisible)
        view_menu.addAction("Consultar rutas completas", self._show_source_paths)
        view_menu.addAction("Cambiar archivos", self._return_to_preparation)
        view_menu.addAction("Nueva comprobación", self._clear)
        preview_header.addWidget(self.view_options)
        self.share_button = QToolButton()
        self.share_button.setText("Compartir")
        self.share_button.setObjectName("reviewShareButton")
        self.share_button.setProperty("reviewMenuButton", True)
        self.share_button.setFocusPolicy(Qt.StrongFocus)
        self.share_button.setToolTip("Exportar la comparación completa o importar una comparación recibida.")
        self.share_button.setAccessibleName("Exportar o importar la comparación completa")
        self.share_button.setPopupMode(QToolButton.InstantPopup)
        share_menu = QMenu(self.share_button)
        share_menu.addAction("Exportar comparación completa…", self._choose_export)
        share_menu.addAction("Importar comparación…", self._choose_import)
        self.share_button.setMenu(share_menu)
        preview_header.addWidget(self.share_button)
        self.detail_button = QPushButton("Detalle del trabajador")
        self.detail_button.setToolTip("Valores de origen y explicación del cálculo (Intro en la tabla)")
        self.detail_button.setEnabled(False)
        self.detail_button.clicked.connect(self._open_worker_detail)
        preview_header.addWidget(self.detail_button)
        preview_layout.addLayout(preview_header)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        section_label = QLabel("Sección")
        filters.addWidget(section_label)
        self.section_filter = QComboBox()
        self.section_filter.setAccessibleName("Filtrar vista previa por sección")
        self.section_filter.currentTextChanged.connect(self._refresh_preview)
        section_label.setBuddy(self.section_filter)
        self.section_filter.setMinimumWidth(150)
        filters.addWidget(self.section_filter)
        self.worker_search = QLineEdit()
        self.worker_search.setPlaceholderText("Nombre, código o incidencia…")
        self.worker_search.setAccessibleName("Buscar por nombre, código o incidencia")
        self.worker_search.setClearButtonEnabled(True)
        self.worker_search.textChanged.connect(lambda *_: self._search_timer.start())
        self.worker_search.setMinimumWidth(180)
        filters.addWidget(self.worker_search, 1)
        reason_label = QLabel("Revisar")
        filters.addWidget(reason_label)
        self.reason_filter = QComboBox()
        self.reason_filter.setAccessibleName("Filtrar por motivo de revisión")
        self.reason_filter.setToolTip("Filtra por el motivo que requiere revisión según las reglas actuales. Las diferencias ordinarias deben superar un minuto; los controles rojos y fichajes siguen sus reglas especiales. No modifica el informe guardado.")
        reason_label.setBuddy(self.reason_filter)
        for title, value in (("Todos los motivos", ""), ("Control: requiere revisión", "Control"),
                             ("Falta de fichaje", "marking"), ("Revisión especial · rojo", "red"),
                             ("Solo en Tempo", "only_tempo"), ("Solo en Partes Mensuales", "only_pm")):
            self.reason_filter.addItem(title, value)
        for name in TIME_COLUMNS:
            self.reason_filter.addItem(f"Revisar {name}", name)
        self.reason_filter.currentIndexChanged.connect(self._refresh_preview)
        filters.addWidget(self.reason_filter)
        incidence_label = QLabel("Incidencia")
        filters.addWidget(incidence_label)
        self.incidence_filter = QComboBox()
        self.incidence_filter.setAccessibleName("Filtrar por incidencia presente en el resultado")
        self.incidence_filter.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.incidence_filter.setMinimumContentsLength(16)
        self.incidence_filter.setMinimumWidth(180)
        self.incidence_filter.setMaximumWidth(250)
        self.incidence_filter.addItem("Todas las incidencias", None)
        self.incidence_filter.setEnabled(False)
        self.incidence_filter.currentIndexChanged.connect(self._refresh_preview)
        self.incidence_filter.currentTextChanged.connect(self.incidence_filter.setToolTip)
        incidence_label.setBuddy(self.incidence_filter)
        filters.addWidget(self.incidence_filter)
        self.reset_filters_button = QPushButton("Quitar filtros")
        self.reset_filters_button.clicked.connect(self._reset_preview_filters)
        filters.addWidget(self.reset_filters_button)
        preview_layout.addLayout(filters)
        self.active_filters = ElidedLabel()
        self.active_filters.setObjectName("activeFilters")
        self.active_filters.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.active_filters.hide()
        preview_layout.addWidget(self.active_filters)
        self.counts_layout = QHBoxLayout()
        self.preview_count = QLabel("Sin resultados")
        self.preview_count.setObjectName("mutedLabel")
        self.preview_count.setWordWrap(True)
        self.preview_count.setToolTip("Los recuentos de origen son anteriores a los filtros de esta vista. Igual cantidad no garantiza las mismas personas. Los trabajadores solo en Tempo sin sección verificable no se asignan a una sección.")
        self.counts_layout.addWidget(self.preview_count)
        self.source_count = QLabel()
        self.source_count.setWordWrap(True)
        self.source_count.setObjectName("mutedLabel")
        self.source_count.setToolTip(self.preview_count.toolTip())
        self.source_count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.counts_layout.addWidget(self.source_count, 1)
        preview_layout.addLayout(self.counts_layout)
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for text, name in (("− Negativo", "legendNegative"), ("+ Positivo", "legendPositive"),
                           ("! Revisión especial", "legendReview")):
            chip = QLabel(text)
            chip.setObjectName(name)
            chip.setToolTip("El color indica signo o regla especial; no significa que el dato esté aprobado.")
            legend.addWidget(chip)
        meaning = QLabel("— Sin comparación aplicable / ambos cero · 0:00 Valores no nulos iguales")
        meaning.setObjectName("mutedLabel")
        meaning.setWordWrap(True)
        meaning.setToolTip("En absentismo, una diferencia cero también se muestra en rojo cuando hay absentismo. Consulta el detalle para ver la regla de cada campo.")
        meaning.hide()
        self.legend_help = QToolButton()
        self.legend_help.setText("Leyenda y ayuda")
        self.legend_help.setObjectName("reviewCompactHelp")
        self.legend_help.clicked.connect(self.show_context_help)
        legend.addWidget(self.legend_help)
        self.counts_layout.addLayout(legend)
        self.review_splitter = QSplitter(Qt.Horizontal)
        self.review_splitter.setChildrenCollapsible(False)
        self.preview_table = FrozenIdentityTable((*RESULT_COLUMNS, "Sección"))
        self.preview_table.setAccessibleName("Vista previa de trabajadores a revisar")
        self.preview_table.setToolTip("Orden fijo: sección y apellidos. Selecciona una fila y pulsa Intro para ver su detalle.")
        self.preview_table.setMinimumHeight(210)
        self.preview_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.review_splitter.addWidget(self.preview_table)
        self.worker_detail = WorkerDetailPanel()
        self.worker_detail.close_requested.connect(self._close_worker_detail)
        self.worker_detail.navigate_requested.connect(self._navigate_worker)
        self.worker_detail.expand_requested.connect(lambda: self._open_worker_detail(expanded=True))
        self.worker_detail.field_selected.connect(self._select_review_field)
        self.review_splitter.addWidget(self.worker_detail)
        self.review_splitter.setStretchFactor(0, 3)
        self.review_splitter.setStretchFactor(1, 1)
        self.review_splitter.splitterMoved.connect(self._remember_detail_width)
        self.worker_detail.hide()
        self.preview_table.set_compact(False)
        self.compact_action.setChecked(str(self._settings.value("comparador/view/compact", "false")).lower() == "true")
        self.accessible_action.setChecked(str(self._settings.value("comparador/view/accessible", "false")).lower() == "true")
        self.preview_table.currentCellChanged.connect(self._preview_selection_changed)
        self.preview_table.cellDoubleClicked.connect(lambda *_: self._open_worker_detail())
        self.preview_table.frozen.doubleClicked.connect(lambda *_: self._open_worker_detail())
        preview_layout.addWidget(self.review_splitter, 1)
        self.empty_preview_label = QLabel("Ningún trabajador coincide con estos filtros. Pulsa «Quitar filtros» para ver el resultado completo.")
        self.empty_preview_label.setObjectName("statusInfo")
        self.empty_preview_label.setWordWrap(True)
        self.empty_preview_label.hide()
        preview_layout.addWidget(self.empty_preview_label)
        actions = QHBoxLayout()
        self.open_result_button = QPushButton("Abrir resultado")
        self.open_result_button.setObjectName("primaryButton")
        self.open_result_button.clicked.connect(self._open_result)
        self.open_incidents_button = QPushButton("Abrir incidencias")
        self.open_incidents_button.clicked.connect(self._open_incidents)
        self.open_folder_button = QPushButton("Abrir carpeta")
        self.open_folder_button.clicked.connect(self._open_folder)
        for button in (self.open_result_button, self.open_incidents_button, self.open_folder_button):
            button.setVisible(False)
            actions.addWidget(button)
        actions.addWidget(self.details_button)
        self.details_button.setText("Registro del proceso")
        self.page_header.layout().removeWidget(self.new_comparison_button)
        self.new_comparison_button.setText("Nueva comparación")
        self.new_comparison_button.setToolTip("Volver al inicio del comparador y limpiar archivos y filtros. No elimina los informes guardados ni las carpetas recordadas.")
        actions.addWidget(self.new_comparison_button)
        actions.addStretch(1)
        order = QLabel("Orden fijo: sección → apellidos")
        order.setObjectName("mutedLabel")
        actions.addWidget(order)
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
        if hasattr(self, "worker_detail") and not self.worker_detail.isHidden() and self.width() < 1450:
            self._close_worker_detail()
            self.detail_button.setToolTip("La ventana se ha reducido. Pulsa para abrir el detalle del trabajador en un diálogo.")

    def _show_view(self, view: str) -> None:
        mapping = {"preparation": self.preparation_state, "processing": self.processing_state, "result": self.result_state}
        widget = mapping[view]
        self.state_stack.setCurrentWidget(widget)
        self.header_status_label.setText({"preparation": "PREPARACIÓN", "processing": "COMPARANDO", "result": "RESULTADO"}[view])
        self.new_comparison_button.setVisible(view == "result")
        self.subtitle_label.setVisible(view == "preparation")
        self.page_header.setVisible(view != "result")
        self.layout().setContentsMargins(*( (12, 10, 12, 10) if view == "result" else (28, 22, 28, 18) ))

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
            (self.tempo_edit, self.tempo_file_name, self.tempo_file_location, self.tempo_file_status, "Partes Mensuales"),
            (self.sap_edit, self.sap_file_name, self.sap_file_location, self.sap_file_status, "Tempo"),
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
        tempo_name = Path(self.tempo_edit.text()).name if self.tempo_edit.text().strip() else "Partes Mensuales pendiente"
        sap_name = Path(self.sap_edit.text()).name if self.sap_edit.text().strip() else "Tempo pendiente"
        self.processing_sources_label.setText(f"Partes Mensuales: {tempo_name}    ·    Tempo: {sap_name}")
        self.result_tempo_chip.setText(f"Partes Mensuales · {tempo_name}")
        self.result_sap_chip.setText(f"Tempo · {sap_name}")

    def _reset_result_presentation(self) -> None:
        self._imported_archive = None
        self.imported_label.hide()
        self._search_timer.stop()
        self._cell_cache.clear()
        self._search_cache.clear()
        self._close_worker_detail()
        self._preview_rows = []
        self.detail_button.setEnabled(False)
        self._last_result = None
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.blockSignals(False)
        self.worker_search.clear()
        self.reason_filter.setCurrentIndex(0)
        self.incidence_filter.blockSignals(True)
        self.incidence_filter.clear()
        self.incidence_filter.addItem("Todas las incidencias", None)
        self.incidence_filter.setEnabled(False)
        self.incidence_filter.blockSignals(False)
        self.preview_table.clearContents()
        self.preview_table.setRowCount(0)
        self.preview_count.setText("Sin resultados")
        self.source_count.clear()
        self.active_filters.hide()
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
        search = QAction(self)
        search.setShortcut("Ctrl+F")
        search.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        search.triggered.connect(lambda: self.worker_search.setFocus() if self.state_stack.currentWidget() is self.result_state else None)
        self.addAction(search)
        for key in ("Return", "Enter"):
            action = QAction(self.preview_table)
            action.setShortcut(key)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(self._open_worker_detail)
            self.preview_table.addAction(action)
        close_detail = QAction(self.result_state)
        close_detail.setShortcut("Esc")
        close_detail.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        close_detail.triggered.connect(self._close_worker_detail)
        self.result_state.addAction(close_detail)

    def _choose_tempo(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(self, "Seleccionar Excel de Partes Mensuales", self.tempo_edit.text() or self._last_directory("pm"), "Excel (*.xlsx *.xlsm)")
        if chosen:
            self._remember_directory("pm", Path(chosen).parent)
            self.tempo_edit.setText(chosen)

    def _choose_sap(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Excel Tempo",
            self.sap_edit.text() or self._last_directory("tempo"),
            "Excel Tempo (*.xlsx *.xlsm *.xls *.xml)",
        )
        if chosen:
            self._remember_directory("tempo", Path(chosen).parent)
            self.sap_edit.setText(chosen)

    def _last_directory(self, kind: str) -> str:
        default = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
        return str(self._settings.value(f"comparador/paths/{kind}", default))

    def _remember_directory(self, kind: str, directory: Path) -> None:
        self._settings.setValue(f"comparador/paths/{kind}", str(directory))
        self._settings.sync()

    def _choose_output(self) -> Path | None:
        default = Path(self._last_directory("output")) / f"Comparador_Tempo_{datetime.now():%Y%m%d}.xlsx"
        chosen, _ = QFileDialog.getSaveFileName(self, "Guardar resultado de comparación", str(default), "Excel (*.xlsx)")
        if not chosen:
            return None
        path = Path(chosen)
        self._remember_directory("output", path.parent)
        return path if path.suffix.lower() == ".xlsx" else path.with_suffix(".xlsx")

    def _start(self) -> None:
        if self.is_running:
            return
        tempo, sap = Path(self.tempo_edit.text().strip()), Path(self.sap_edit.text().strip())
        if not tempo.is_file() or not sap.is_file():
            QMessageBox.warning(self, "Archivos pendientes", "Selecciona un Excel de Partes Mensuales y un Excel Tempo disponibles.")
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
        self._details = [f"Partes Mensuales: {tempo}", f"Tempo: {sap}", f"Salida: {output}", "-" * 48]
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
        return result_from_payload(data)

    def _choose_import(self) -> None:
        if self.is_running:
            return
        chosen, _ = QFileDialog.getOpenFileName(self, "Importar comparación completa", self._last_directory("exchange"), "Comparación Suite RRHH (*.rrhh)")
        if chosen:
            self._import_comparison(Path(chosen))

    def _import_comparison(self, path: Path) -> None:
        if self.is_running:
            return
        if self._last_result is not None and QMessageBox.question(
            self, "Abrir otra comparación", "Se sustituirá la vista actual. Los informes guardados no se borrarán. ¿Continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self._run_transfer(lambda: load_archive(path), lambda archive: self._show_imported(archive, path), "Abriendo comparación…")

    def _show_imported(self, archive, path) -> None:
        self._reset_result_presentation()
        self.tempo_edit.clear()
        self.sap_edit.clear()
        self._details.clear()
        self._imported_archive = archive
        self._on_success(archive.result)
        self._remember_directory("exchange", path.parent)

    def _choose_export(self) -> None:
        if self.is_running or self._last_result is None:
            return
        filename = Path(self._last_directory("exchange")) / f"Comparacion_{datetime.now():%Y%m%d}.rrhh"
        chosen, _ = QFileDialog.getSaveFileName(self, "Exportar comparación completa", str(filename), "Comparación Suite RRHH (*.rrhh)")
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() != '.rrhh':
            path = path.with_suffix('.rrhh')
            if path.exists() and QMessageBox.question(self, "Sustituir archivo", "El archivo .rrhh ya existe. ¿Sustituirlo?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        if QMessageBox.question(self, "Compartir datos de trabajadores",
            "Se exportará la comparación COMPLETA, aunque tengas filtros activos, y los dos informes. "
            "Incluye nombres, códigos, horas e incidencias. No está cifrada: envíala solo a destinatarios autorizados.\n\n¿Continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        result, imported = self._last_result, self._imported_archive
        def export():
            snapshot_rows = tuple(replace(row, review_snapshot={field: {
                'explanation': calculation_text(row, field), 'triplet': list(comparison_triplet(row, field))
            } for field in ('Trab. Día Tempo', 'Control', *TIME_COLUMNS)}) for row in result.rows)
            return save_archive(path, replace(result, rows=snapshot_rows),
                                reports=imported.reports if imported else None,
                                created_at=imported.created_at if imported else None,
                                app_version=imported.app_version if imported else None)
        def saved(value):
            self._remember_directory("exchange", path.parent)
            QMessageBox.information(self, "Comparación exportada", "Archivo listo para compartir:\n" + str(value) + "\n\nEl destinatario debe usar Importar comparación en una versión compatible de Suite RRHH.")
        self._run_transfer(export, saved, "Exportando comparación completa…")

    def _run_transfer(self, operation, completed, message) -> None:
        if self.is_running:
            return
        progress = QProgressDialog(message, "", 0, 0, self)
        progress.setWindowTitle("Comparación · Intercambio")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        worker = BackgroundTask(operation, self)
        self._transfer_thread = worker
        def finished():
            self._transfer_thread = None
            progress.close()
            progress.deleteLater()
            try:
                if worker.error:
                    QMessageBox.warning(self, "No se pudo completar el intercambio", worker.error)
                else:
                    completed(worker.value)
            finally:
                worker.deleteLater()
        worker.finished.connect(finished)
        progress.show()
        worker.start()

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not self.is_running and len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == '.rrhh':
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not self.is_running and len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == '.rrhh':
            event.acceptProposedAction()
            self._import_comparison(Path(urls[0].toLocalFile()))

    def _save_imported_report(self, name) -> None:
        chosen, _ = QFileDialog.getSaveFileName(self, "Guardar copia del informe recibido", str(Path(self._last_directory('output')) / name), "Excel (*.xlsx)")
        if not chosen:
            return
        target = Path(chosen)
        if target.suffix.lower() != '.xlsx':
            target = target.with_suffix('.xlsx')
            if target.exists() and QMessageBox.question(self, "Sustituir informe", "El informe ya existe. ¿Sustituirlo?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        content = self._imported_archive.reports[name]
        def save():
            fd, temporary = tempfile.mkstemp(prefix='.rrhh-report-', dir=target.parent)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return target
        def saved(path):
            self._remember_directory('output', path.parent)
            QMessageBox.information(self, "Informe guardado", str(path))
        self._run_transfer(save, saved, "Guardando copia del informe…")


    def _on_success(self, result: ComparatorResult) -> None:
        self._search_timer.stop()
        self._cell_cache.clear()
        self._search_cache = {id(row): search_key(" ".join((row.worker, row.sap_code, *row.incidence_messages))) for row in result.rows}
        self._close_worker_detail()
        self._last_result = result
        if self._imported_archive is None:
            self._remember_directory("output", result.output_path.parent)
        self._details.extend(result.detail_lines)
        self.progress.setValue(self.progress.maximum())
        self._set_status(f"Comparación terminada: {len(result.rows)} trabajadores para revisar y {len(result.incidents)} incidencias auditables.", "statusSuccess")
        self.workers_value_label.setText(f"{len(result.rows)} en el informe")
        self.incidents_value_label.setText(f"{len(result.incidents)} registros de auditoría")
        elapsed = int(result.elapsed_seconds)
        self.result_summary_label.setText(f"Completada · {elapsed // 60:02d}:{elapsed % 60:02d}")
        self.section_filter.blockSignals(True)
        self.section_filter.clear()
        self.section_filter.addItem("Todas las secciones")
        for section in sorted(set(result.sections) | set(result.section_counts), key=lambda value: (not bool(value), search_key(value))):
            self.section_filter.addItem(section or "Sin sección verificable", section)
        if any(row.missing_source for row in result.rows):
            self.section_filter.addItem("Solo en un origen", "__missing__")
        self.section_filter.blockSignals(False)
        self.reason_filter.blockSignals(True)
        self.reason_filter.setCurrentIndex(0)
        self.reason_filter.blockSignals(False)
        self.incidence_filter.blockSignals(True)
        self.incidence_filter.clear()
        self.incidence_filter.addItem("Todas las incidencias", None)
        options = {}
        for row in result.rows:
            for message in row.incidence_messages:
                label = " ".join(message.split())
                if label not in {"", "-", "—"}:
                    options.setdefault(label.casefold(), label)
        if any(not incidence_keys(row) for row in result.rows):
            self.incidence_filter.addItem("Sin incidencias", "")
        for key, label in sorted(options.items(), key=lambda item: search_key(item[1])):
            self.incidence_filter.addItem(label, key)
        self.incidence_filter.setEnabled(bool(result.rows))
        self.incidence_filter.setToolTip("Incidencias presentes en el resultado completo; se combina con sección, motivo y búsqueda.")
        self.incidence_filter.blockSignals(False)
        self.worker_search.blockSignals(True)
        self.worker_search.clear()
        self.worker_search.blockSignals(False)
        self._refresh_preview()
        for button in (self.open_result_button, self.open_incidents_button, self.open_folder_button):
            button.setVisible(True)
        self._show_view("result")
        imported = self._imported_archive
        self.imported_label.setVisible(imported is not None)
        self.sources_action.setEnabled(imported is None)
        self.sources_action.setChecked(False)
        self.open_result_button.setText("Guardar resultado" if imported else "Abrir resultado")
        self.open_incidents_button.setText("Guardar incidencias" if imported else "Abrir incidencias")
        self.open_folder_button.setVisible(imported is None)
        if imported:
            self.imported_label.setText(f"Comparación importada · Modo consulta · Exportada {imported.created_at} · Versión {imported.app_version} · Resultado completo, sin recalcular")
            self.result_summary_label.setText("Comparación importada · Solo consulta")
            self.details_button.setEnabled(False)
        self.section_filter.setFocus()

    def _refresh_preview(self) -> None:
        self._search_timer.stop()
        result = self._last_result
        if result is None:
            self.preview_table.setRowCount(0)
            self.preview_count.setText("Sin resultados")
            return
        selection = self.section_filter.currentData()
        rows = [row for row in result.rows if selection is None
                or (bool(row.missing_source) if selection == "__missing__" else row.section == selection)]
        section_rows = rows
        rows = [row for row in rows if matches_reason(row, self.reason_filter.currentData())]
        rows = [row for row in rows if matches_incidence(row, self.incidence_filter.currentData())]
        needle = search_key(self.worker_search.text().strip()).split()
        if needle:
            rows = [
                row for row in rows
                if all(word in self._search_cache.get(id(row), "") for word in needle)
            ]
        rows = sorted(rows, key=review_order)
        previous = self.preview_table.currentRow()
        identity = None
        if 0 <= previous < len(self._preview_rows):
            old = self._preview_rows[previous]
            identity = (old.section, old.sap_code, old.missing_source)
        rows_changed = rows != self._preview_rows
        self._preview_rows = rows
        self.preview_table.setUpdatesEnabled(False)
        self.preview_table.blockSignals(True)
        if rows_changed:
            self.preview_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows if rows_changed else []):
            cached = self._cell_cache.get(id(row))
            if cached is not None:
                for column, prototype in enumerate(cached):
                    self.preview_table.setItem(row_index, column, QTableWidgetItem(prototype))
                continue
            incidence_text = "; ".join(row.incidence_messages) if row.incidence_messages else "—"
            if row.missing_source:
                incidence_text += f" · Sección: {row.section or 'Sin asignar'}"
            values = [
                row.sap_code,
                row.worker,
                incidence_text,
                "—" if row.missing_source else self._format_minutes(row.sap_daily_work_minutes),
                "—" if "Control" in row.suppressed_fields else self._format_difference(row.sap_daily_minus_noise_minutes or 0),
                *[
                    "—" if column in row.suppressed_fields else (
                        self._format_minutes(row.values_minutes.get(column, 0))
                        if column in row.red_fields else self._format_difference(row.values_minutes.get(column, 0))
                    )
                    for column in TIME_COLUMNS[:-1]
                ],
                self._format_difference(row.values_minutes.get("ABSENT", 0)) if "ABSENT" in row.red_fields else "—",
                row.section or "Sin verificar",
            ]
            field_by_column = {4: "Control", **{5 + index: field for index, field in enumerate(TIME_COLUMNS)}}
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"Sección: {row.section or 'Sin asignar'} · Código Tempo: {row.sap_code}\n{value}")
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter if column in {0, 1, 2} else Qt.AlignCenter)
                field = field_by_column.get(column)
                if field is not None:
                    item.setToolTip(calculation_text(row, field))
                    minutes = row.sap_daily_minus_noise_minutes if field == "Control" else row.values_minutes.get(field, 0)
                    colors = comparison_colors(minutes, red=field in row.red_fields, suppressed=value == "—")
                    if colors:
                        item.setBackground(QColor("#" + colors[0]))
                        item.setForeground(QColor("#" + colors[1]))
                self.preview_table.setItem(row_index, column, item)
                item.setData(Qt.AccessibleTextRole, f"{self.preview_table.horizontalHeaderItem(column).text()}: {value}")
                item.setData(Qt.AccessibleDescriptionRole, item.toolTip())
            self._cell_cache[id(row)] = tuple(QTableWidgetItem(self.preview_table.item(row_index, column)) for column in range(len(values)))
        self.preview_table.blockSignals(False)
        self.preview_table.setUpdatesEnabled(True)
        self.preview_table.frozen.viewport().update()
        self.detail_button.setEnabled(bool(rows))
        if rows:
            selected = next((i for i, row in enumerate(rows) if (row.section, row.sap_code, row.missing_source) == identity), 0)
            self.preview_table.setCurrentCell(selected, max(0, self.preview_table.currentColumn()))
            self._preview_selection_changed()
        else:
            self._close_worker_detail()
        self.empty_preview_label.setVisible(not rows)
        self.empty_preview_label.setText("Ningún trabajador coincide con estos filtros. Pulsa «Quitar filtros» para ver el resultado completo." if result.rows else "La comparación no ha incluido trabajadores para revisar. Consulta la auditoría para comprobar posibles avisos de los datos de origen.")
        self.reset_filters_button.setEnabled(selection is not None or bool(needle) or bool(self.reason_filter.currentData()) or self.incidence_filter.currentData() is not None)
        counts = result.section_counts.get(selection)
        self.source_count.setToolTip(self.preview_count.toolTip())
        count_text = f"Vista: {len(rows)} de {len(section_rows)}"
        source_text = ""
        if counts is not None:
            source_text = f"Orígenes de {selection}: Partes Mensuales: {counts['pm']} · Tempo: {counts['tempo']}"
        elif selection is None and result.section_counts:
            only_tempo = sum(row.missing_source == "Partes Mensuales" for row in result.rows)
            source_text = f"Por sección: PM {sum(c['pm'] for c in result.section_counts.values())} · Tempo vinculado {sum(c['tempo'] for c in result.section_counts.values())}"
            self.source_count.setToolTip(self.preview_count.toolTip() + f"\nTrabajadores solo en Tempo: {only_tempo}.")
        elif selection != "__missing__":
            source_text = "Recuentos de origen no disponibles"
        self.preview_count.setText(count_text)
        self.source_count.setText(source_text)
        active = []
        if selection is not None:
            active.append("Sección: " + self.section_filter.currentText())
        if self.reason_filter.currentData():
            active.append(self.reason_filter.currentText())
        if self.incidence_filter.currentData() is not None:
            active.append("Incidencia: " + self.incidence_filter.currentText())
        if needle:
            active.append("Búsqueda: " + self.worker_search.text().strip())
        self.active_filters.setText("Filtros activos · " + " · ".join(active))
        self.active_filters.setVisible(bool(active))

    def _reset_preview_filters(self) -> None:
        for control in (self.section_filter, self.reason_filter, self.incidence_filter, self.worker_search):
            control.blockSignals(True)
        self.section_filter.setCurrentIndex(0)
        self.reason_filter.setCurrentIndex(0)
        self.incidence_filter.setCurrentIndex(0)
        self.worker_search.clear()
        for control in (self.section_filter, self.reason_filter, self.incidence_filter, self.worker_search):
            control.blockSignals(False)
        self._refresh_preview()
        self.worker_search.setFocus()

    def _selected_review_row(self) -> ComparatorRow | None:
        index = self.preview_table.currentRow()
        return self._preview_rows[index] if 0 <= index < len(self._preview_rows) else None

    def _set_review_tab_order(self) -> None:
        controls = (self.result_back_button, self.paths_button, self.view_options, self.share_button, self.section_filter, self.worker_search,
                    self.reason_filter, self.incidence_filter, self.reset_filters_button, self.legend_help,
                    self.preview_table, self.detail_button, self.worker_detail.expand_button, self.worker_detail.close_button,
                    self.worker_detail.previous_button, self.worker_detail.next_button,
                    self.worker_detail.all_fields, self.worker_detail.browser,
                    self.open_result_button, self.open_incidents_button, self.open_folder_button,
                    self.details_button, self.new_comparison_button)
        for first, second in zip(controls, controls[1:]):
            QWidget.setTabOrder(first, second)

    def _set_compact_view(self, compact: bool) -> None:
        self.preview_table.set_compact(compact)
        self._settings.setValue("comparador/view/compact", compact)

    def _set_accessible_view(self, enabled: bool) -> None:
        self.preview_table.set_accessible_mode(enabled)
        self._settings.setValue("comparador/view/accessible", enabled)

    def _remember_detail_width(self, *args) -> None:
        if not self.worker_detail.isHidden():
            self._detail_width = self.review_splitter.sizes()[1]

    def _navigate_worker(self, step: int) -> None:
        index = self.preview_table.currentRow() + step
        if 0 <= index < len(self._preview_rows):
            self.preview_table.setCurrentCell(index, self.preview_table.currentColumn())

    def _show_source_paths(self) -> None:
        if self._imported_archive:
            QMessageBox.information(self, "Comparación recibida", "Esta comparación no necesita los Excel originales. Usa Guardar resultado o Guardar incidencias para obtener una copia de los informes recibidos.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Archivos de la comprobación")
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.resize(min(850, self.width() - 40), 330)
        layout = QVBoxLayout(dialog)
        sources = [("Partes Mensuales", self.tempo_edit.text()), ("Tempo", self.sap_edit.text())]
        if self._last_result is not None:
            sources.extend((("Informe de diferencias", str(self._last_result.output_path)),
                            ("Informe de incidencias", str(self._last_result.incidents_path))))
        for title, path in sources:
            layout.addWidget(QLabel(title))
            row = QHBoxLayout()
            edit = QLineEdit(path or "Sin archivo seleccionado")
            edit.setReadOnly(True)
            edit.setAccessibleName(f"Ruta completa de {title}")
            edit.setCursorPosition(0)
            row.addWidget(edit, 1)
            copy = QPushButton("Copiar ruta")
            copy.setAccessibleName(f"Copiar ruta de {title}")
            copy.setEnabled(bool(path))
            copy.clicked.connect(lambda checked=False, value=path: QApplication.clipboard().setText(value))
            row.addWidget(copy)
            layout.addLayout(row)
        close = QPushButton("Cerrar")
        close.clicked.connect(dialog.close)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.show()


    def _selected_review_field(self) -> str | None:
        return {3: "Trab. Día Tempo", 4: "Control", **{5 + i: field for i, field in enumerate(TIME_COLUMNS)}}.get(self.preview_table.currentColumn())

    def _select_review_field(self, field: str) -> None:
        columns = {"Trab. Día Tempo": 3, "Control": 4, **{name: 5 + i for i, name in enumerate(TIME_COLUMNS)}}
        if field in columns and self.preview_table.currentRow() >= 0:
            self.preview_table.setCurrentCell(self.preview_table.currentRow(), columns[field])

    def _preview_selection_changed(self, *args) -> None:
        row = self._selected_review_row()
        if row and not self.worker_detail.isHidden():
            self.worker_detail.show_worker(row, self._selected_review_field())
            self.worker_detail.set_position(self.preview_table.currentRow(), len(self._preview_rows))
        if row and self._dialog_detail_panel is not None:
            self._dialog_detail_panel.show_worker(row, self._selected_review_field())
            self._dialog_detail_panel.set_position(self.preview_table.currentRow(), len(self._preview_rows))

    def _open_worker_detail(self, *, expanded: bool = False) -> None:
        row = self._selected_review_row()
        if row is None:
            return
        if self.width() < 1450 or expanded:
            if self._detail_dialog is not None:
                self._detail_dialog.raise_()
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Detalle del trabajador · Comparador de Tempo")
            dialog.setAttribute(Qt.WA_DeleteOnClose)
            dialog.setWindowModality(Qt.WindowModal)
            dialog.resize(min(1200 if expanded else 900, self.width() - 40), min(920, self.height() - 40))
            panel = WorkerDetailPanel(dialog)
            panel.expand_button.hide()
            panel.show_worker(row, self._selected_review_field())
            panel.set_position(self.preview_table.currentRow(), len(self._preview_rows))
            panel.navigate_requested.connect(self._navigate_worker)
            panel.field_selected.connect(self._select_review_field)
            panel.close_requested.connect(dialog.close)
            layout = QVBoxLayout(dialog)
            layout.addWidget(panel)
            self._detail_dialog = dialog
            self._dialog_detail_panel = panel
            dialog.finished.connect(self._detail_dialog_finished)
            dialog.show()
            panel.close_button.setFocus()
        else:
            self.worker_detail.show_worker(row, self._selected_review_field())
            self.worker_detail.set_position(self.preview_table.currentRow(), len(self._preview_rows))
            self.worker_detail.show()
            self.review_splitter.setSizes([max(600, self.review_splitter.width() - self._detail_width), self._detail_width])
            self.worker_detail.close_button.setFocus()

    def _detail_dialog_finished(self, *args) -> None:
        self._detail_dialog = None
        self._dialog_detail_panel = None
        self.preview_table.setFocus()

    def _close_worker_detail(self) -> None:
        if self._detail_dialog is not None:
            self._detail_dialog.close()
        self.worker_detail.hide()
        if self.state_stack.currentWidget() is self.result_state:
            self.preview_table.setFocus()

    @staticmethod
    def _format_minutes(minutes: int | None) -> str:
        return duration(minutes or 0)

    @staticmethod
    def _format_difference(minutes: int) -> str:
        return duration(minutes, signed=True)

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
        if self._imported_archive:
            self._save_imported_report('resultado.xlsx')
            return
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path)))

    def _open_incidents(self) -> None:
        if self._imported_archive:
            self._save_imported_report('incidencias.xlsx')
            return
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.incidents_path)))

    def _open_folder(self) -> None:
        if self._last_result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_path.parent)))

    def show_context_help(self) -> None:
        ComparadorTempoHelpDialog(self).exec()

    def request_leave(self) -> bool:
        if self._transfer_thread is not None:
            QMessageBox.information(self, "Intercambio en curso", "Espera a que termine la importación o exportación antes de salir.")
            return False
        if not self.is_running:
            return True
        answer = QMessageBox.question(self, "Comparación en curso", "Hay una comparación en curso. ¿Solicitar su cancelación?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._cancel()
        return False
