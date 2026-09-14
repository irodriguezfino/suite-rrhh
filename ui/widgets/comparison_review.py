"""Read-only review components. No workbook access or comparison decisions here."""

from __future__ import annotations

from html import escape
import unicodedata

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QTableWidget,
    QTextBrowser, QVBoxLayout,
)

from core.models import ComparatorRow
from core.comparison_style import comparison_colors
from ui.theme import COLORS
from services.comparador_tempo_service import (
    COMBINED_EXTRA_BOLSA_SECTIONS, MISSING_MARKING_MESSAGES, SAP_FIELD_BY_TEMPO,
    SPECIAL_NOCTURNITY_SECTIONS, SPECIAL_NOISE_SECTIONS, TIME_COLUMNS,
)


class ElidedLabel(QLabel):
    """A compact one-line label whose complete text remains accessible."""

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._elide()

    def _elide(self):
        super().setText(self.fontMetrics().elidedText(getattr(self, "_full_text", ""), Qt.ElideMiddle, max(0, self.contentsRect().width() - 16)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


def search_key(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold())
                   if unicodedata.category(c) != "Mn")


def review_order(row: ComparatorRow) -> tuple:
    # Source names already follow SURNAME(S), GIVEN NAME. Do not guess surnames.
    return (not bool(row.section), search_key(row.section), search_key(row.worker), row.sap_code)


def matches_reason(row: ComparatorRow, reason: str | None) -> bool:
    if not reason:
        return True
    if reason == "marking":
        return any(message in MISSING_MARKING_MESSAGES for message in row.incidence_messages)
    if reason == "red":
        return bool(row.red_fields)
    if reason == "only_tempo":
        return row.missing_source == "Partes Mensuales"
    if reason == "only_pm":
        return row.missing_source == "Tempo"
    return reason in row.trigger_fields


def duration(minutes: int | None, signed: bool = False) -> str:
    if minutes is None:
        return "No disponible"
    sign = "−" if minutes < 0 else "+" if signed and minutes > 0 else ""
    hours, remainder = divmod(abs(minutes), 60)
    return f"{sign}{hours}:{remainder:02d}"


def calculation_text(row: ComparatorRow, field: str) -> str:
    """Explain the existing result, using recorded originals, including exceptions."""
    if row.missing_source:
        return f"No aparece en {row.missing_source}. No se comparan valores; el informe muestra —."
    if field == "Trab. Día Tempo":
        return f"Total de trabajo diario de Tempo: {duration(row.sap_daily_work_minutes)}. Es un dato de origen, no una diferencia."
    if not row.pm_source_minutes or not row.tempo_source_minutes:
        return "Los valores de origen no están disponibles en este resultado. Vuelve a comprobar los archivos para ver el desglose."
    pm = row.pm_source_minutes
    tempo = row.tempo_source_minutes
    section = row.section.upper().strip()
    if field == "H. EXTRAS" and section in COMBINED_EXTRA_BOLSA_SECTIONS:
        return "En esta sección las horas extra de PM se suman a Bolsa. El informe muestra — aquí; consulta Bolsa (X%)."
    direct = ((field == "RUIDO" and section in SPECIAL_NOISE_SECTIONS)
              or (field == "NOCTUR" and section in SPECIAL_NOCTURNITY_SECTIONS))
    source_field = "Trab. Dia" if field == "Control" else SAP_FIELD_BY_TEMPO[field]
    pm_field = "RUIDO" if field == "Control" else field
    left = tempo.get(source_field)
    right = pm.get(pm_field)
    if left is None or right is None:
        return "Faltan valores de origen para explicar este campo; no se presuponen ceros."
    if direct:
        return (f"Regla especial de {section}: Tempo · {source_field} = {duration(left)}. "
                + ("Se muestra este valor en rojo para revisar; no es una resta." if left else
                   "Sin valor en Tempo: el informe muestra —, independientemente de PM."))
    pm_caption = f"PM · {pm_field}: {duration(right)}"
    if field == "BOLSA (X%)" and section in COMBINED_EXTRA_BOLSA_SECTIONS:
        extra = pm.get("H. EXTRAS")
        if extra is None:
            return "No están disponibles las horas extra de PM para explicar la comparación conjunta."
        pm_caption = f"PM · H. EXTRAS {duration(extra)} + Bolsa {duration(right)} = {duration(extra + right)}"
        right += extra
    explanation = f"Tempo · {source_field}: {duration(left)}\n{pm_caption}\n{duration(left)} − {duration(right)} = {duration(left - right, signed=True)}"
    if field in row.suppressed_fields:
        explanation += "\nAmbos valores son cero: el informe muestra —."
    elif field == "ABSENT":
        explanation += "\nHay absentismo en al menos un origen: la diferencia se muestra en rojo, incluso si es cero."
    elif left == right:
        explanation += "\nLos valores coinciden y no son cero: se muestra 0:00."
    return explanation


def comparison_triplet(row: ComparatorRow, field: str) -> tuple[str, str, str, str]:
    """Presentation of recorded totals; direct controls are never labelled deltas."""
    if row.missing_source:
        return ("—", "—", "—", "Sin comparación")
    if field == "Trab. Día Tempo":
        return (duration(row.sap_daily_work_minutes), "—", "—", "Dato de origen")
    source = "Trab. Dia" if field == "Control" else SAP_FIELD_BY_TEMPO[field]
    pm_field = "RUIDO" if field == "Control" else field
    left = row.tempo_source_minutes.get(source)
    right = row.pm_source_minutes.get(pm_field)
    combined = row.section.upper().strip() in COMBINED_EXTRA_BOLSA_SECTIONS
    if combined and field == "BOLSA (X%)":
        extra = row.pm_source_minutes.get("H. EXTRAS")
        right = extra + right if extra is not None and right is not None else None
    section = row.section.upper().strip()
    direct = ((field == "RUIDO" and section in SPECIAL_NOISE_SECTIONS)
              or (field == "NOCTUR" and section in SPECIAL_NOCTURNITY_SECTIONS))
    value = row.sap_daily_minus_noise_minutes if field == "Control" else row.values_minutes.get(field)
    shown = "—" if field in row.suppressed_fields or (field == "ABSENT" and field not in row.red_fields) else duration(value, signed=not direct)
    return duration(left), duration(right), shown, "Valor a revisar" if direct else "Diferencia"


class DifferenceDelegate(QStyledItemDelegate):
    """Keep sign/review colors legible even when a whole row is selected."""

    def paint(self, painter, option, index):
        colored = index.data(Qt.BackgroundRole)
        if option.state & QStyle.State_Selected:
            clean = QStyleOptionViewItem(option)
            if colored is not None:
                clean.state &= ~QStyle.State_Selected
            else:
                clean.palette.setColor(QPalette.Highlight, QColor(COLORS["info_surface"]))
                clean.palette.setColor(QPalette.HighlightedText, QColor(COLORS["text"]))
            super().paint(painter, clean, index)
            painter.save()
            painter.setPen(QPen(option.palette.highlight().color(), 1))
            painter.drawLine(option.rect.topLeft(), option.rect.topRight())
            painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
            if index.column() == index.model().columnCount() - 1:
                painter.fillRect(option.rect.left(), option.rect.top(), 3, option.rect.height(), QColor(COLORS["focus"]))
            painter.restore()
        else:
            super().paint(painter, option, index)


class FrozenIdentityTable(QTableWidget):
    """One model; section, code and surname remain visible in the frozen view."""

    DEFAULT_WIDTHS = (100, 275, 230, 135, 110, 115, 115, 125, 115, 110, 110, 110, 90)

    def __init__(self, columns: tuple[str, ...], parent=None):
        super().__init__(0, len(columns), parent)
        self.setObjectName("reviewTable")
        self._accessible_mode = False
        self.identity_columns = (len(columns) - 1, 0, 1)
        self.setHorizontalHeaderLabels(columns)
        self.setSortingEnabled(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(36)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setMinimumSectionSize(80)
        self.horizontalHeader().setSectionsMovable(False)
        self.horizontalHeader().setSectionsClickable(False)
        self.horizontalHeader().moveSection(len(columns) - 1, 0)
        self.setItemDelegate(DifferenceDelegate(self))
        self.frozen = QTableView(self)
        self.frozen.setObjectName("frozenIdentity")
        self.frozen.setModel(self.model())
        self.frozen.setSelectionModel(self.selectionModel())
        self.frozen.setFocusPolicy(Qt.NoFocus)
        self.frozen.setAccessibleName("Código y trabajador fijos; selección compartida con la tabla")
        self.frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.frozen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.frozen.setSelectionMode(QAbstractItemView.SingleSelection)
        self.frozen.setAlternatingRowColors(True)
        self.frozen.setWordWrap(False)
        self.frozen.setTextElideMode(Qt.ElideRight)
        self.frozen.verticalHeader().hide()
        self.frozen.verticalHeader().setDefaultSectionSize(36)
        self.frozen.horizontalHeader().setSectionsClickable(False)
        self.frozen.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.frozen.horizontalHeader().setMinimumSectionSize(80)
        self.frozen.horizontalHeader().moveSection(len(columns) - 1, 0)
        self.frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.frozen.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.frozen.setItemDelegate(DifferenceDelegate(self.frozen))
        for column in range(len(columns)):
            if column not in self.identity_columns:
                self.frozen.hideColumn(column)
        self.verticalScrollBar().valueChanged.connect(self.frozen.verticalScrollBar().setValue)
        self.frozen.verticalScrollBar().valueChanged.connect(self.verticalScrollBar().setValue)
        self.horizontalHeader().sectionResized.connect(self._resize_frozen_column)
        self.frozen.horizontalHeader().sectionResized.connect(self._resize_from_frozen)
        self.verticalHeader().sectionResized.connect(lambda row, old, size: self.frozen.setRowHeight(row, size))
        self.reset_column_widths()
        self.frozen.show()

    def reset_column_widths(self):
        for col, width in enumerate(self.DEFAULT_WIDTHS[:self.columnCount()]):
            self.setColumnWidth(col, width)

    def _resize_from_frozen(self, column, old, width):
        if column in self.identity_columns:
            self.setColumnWidth(column, width)

    def set_compact(self, compact: bool):
        height = max(30 if compact else 38, self.fontMetrics().height() + (10 if compact else 18))
        self.verticalHeader().setDefaultSectionSize(height)
        self.frozen.verticalHeader().setDefaultSectionSize(height)

    def set_accessible_mode(self, enabled: bool):
        # A single native table avoids duplicate accessible table representations.
        self._accessible_mode = enabled
        self.frozen.setVisible(not enabled)
        self.setAccessibleDescription("Tabla única para lector de pantalla; todas las columnas se desplazan." if enabled else
                                      "Sección, código y nombre fijos. Activa Lectura accesible para usar una única tabla.")
        self.setFocus()

    def _identity_width(self):
        return 0 if self._accessible_mode else sum(self.columnWidth(col) for col in self.identity_columns)

    def _resize_frozen_column(self, column, old, width):
        if column in self.identity_columns:
            # Leave room for at least one data column on small windows.
            maximum = max(110, self.viewport().width() - 240 - sum(self.columnWidth(col) for col in self.identity_columns if col != column)) if self.isVisible() else 480
            maximum = min(maximum, 480 if column == 1 else 150)
            if width > maximum:
                self.setColumnWidth(column, maximum)
                return
            self.frozen.setColumnWidth(column, width)
            self._position_frozen()

    def _position_frozen(self):
        if not hasattr(self, "frozen"):
            return
        width = self._identity_width()
        self.frozen.setGeometry(self.frameWidth(), self.frameWidth(), width,
                                self.viewport().height() + self.horizontalHeader().height())
        self.frozen.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "frozen"):
            for column in self.identity_columns:
                self._resize_frozen_column(column, 0, self.columnWidth(column))
        self._position_frozen()

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible):
        previous = self.horizontalScrollBar().value()
        super().scrollTo(index, hint)
        if self._accessible_mode:
            return
        if index.column() in self.identity_columns:
            self.horizontalScrollBar().setValue(previous)
        elif self.visualRect(index).left() < self._identity_width():
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() + self.visualRect(index).left()
                - self._identity_width())


class WorkerDetailPanel(QFrame):
    close_requested = Signal()
    navigate_requested = Signal(int)
    expand_requested = Signal()
    field_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workerDetailPanel")
        self.setMinimumWidth(330)
        self._row = None
        self._field = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.identity_label = QLabel("Detalle del trabajador")
        self.identity_label.setObjectName("sectionLabel")
        self.identity_label.setWordWrap(True)
        self.identity_label.setTextFormat(Qt.PlainText)
        header.addWidget(self.identity_label, 1)
        self.expand_button = QPushButton("Ampliar")
        self.expand_button.setToolTip("Abrir el detalle en una ventana amplia; Esc para volver a la tabla")
        self.expand_button.clicked.connect(self.expand_requested.emit)
        header.addWidget(self.expand_button, 0, Qt.AlignTop)
        self.close_button = QPushButton("Cerrar")
        self.close_button.setToolTip("Cerrar el detalle (Esc)")
        self.close_button.clicked.connect(self.close_requested.emit)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        self.reason_label = QLabel()
        self.reason_label.setWordWrap(True)
        self.reason_label.setTextFormat(Qt.PlainText)
        self.reason_label.setObjectName("mutedLabel")
        layout.addWidget(self.reason_label)
        navigation = QHBoxLayout()
        self.previous_button = QPushButton("← Anterior")
        self.next_button = QPushButton("Siguiente →")
        self.position_label = QLabel()
        self.position_label.setObjectName("mutedLabel")
        self.previous_button.clicked.connect(lambda: self.navigate_requested.emit(-1))
        self.next_button.clicked.connect(lambda: self.navigate_requested.emit(1))
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.position_label, 1, Qt.AlignCenter)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)
        self.all_fields = QCheckBox("Ver todos los campos")
        self.all_fields.setToolTip("Por defecto se muestran los motivos de revisión y el campo seleccionado en la tabla.")
        self.all_fields.toggled.connect(self._render)
        layout.addWidget(self.all_fields)
        self.browser = QTextBrowser()
        self.browser.setAccessibleName("Valores originales, motivos de revisión y cálculos del trabajador")
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._choose_field)
        layout.addWidget(self.browser)

    def _choose_field(self, url):
        fragment = url.fragment()
        if not fragment.startswith("concept") or not fragment[7:].isdigit():
            return
        index = int(fragment[7:])
        fields = ("Trab. Día Tempo", "Control", *TIME_COLUMNS)
        if index >= len(fields):
            return
        self._field = fields[index]
        self._render()
        self.field_selected.emit(self._field)

    def set_position(self, index: int, total: int):
        self.position_label.setText(f"{index + 1} / {total}")
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < total)

    def show_worker(self, row: ComparatorRow, field: str | None = None):
        if self._row == row and self._field == field:
            return
        self._row, self._field = row, field
        self._render()

    def _render(self, *args):
        row, field = self._row, self._field
        if row is None:
            return
        reasons = []
        if row.trigger_fields:
            reasons.append("Campos que requieren revisión: " + ", ".join(row.trigger_fields))
        reasons.extend(row.incidence_messages)
        if not reasons:
            reasons.append("Consulta los campos del resultado y sus reglas de revisión.")
        self.identity_label.setText(f"{row.worker}\n{row.sap_code} · {row.section or 'Sin sección verificable'}")
        self.reason_label.setText("Motivo: " + (f"No aparece en {row.missing_source}" if row.missing_source else
                                  ", ".join(row.trigger_fields) or "Incidencia / identidad pendiente"))
        self.reason_label.setToolTip("\n".join(reasons))
        blocks = []
        if row.incidence_messages:
            blocks.append("<p>" + "<br>".join(escape(message) for message in row.incidence_messages) + "</p>")
        fields = ("Trab. Día Tempo", "Control", *TIME_COLUMNS)
        relevant = set(row.trigger_fields) | set(row.red_fields)
        if field:
            relevant.add(field)
        ordered = [name for name in fields if name in relevant]
        if self.all_fields.isChecked():
            ordered += [name for name in fields if name not in relevant]
        if not ordered:
            blocks.append("<p>No hay campos numéricos que requieran revisión. Consulta la incidencia indicada arriba o activa «Ver todos los campos».</p>")
        else:
            blocks.append('<p>Selecciona un concepto para ver su cálculo. <b>PM</b> = Partes Mensuales.</p>')
            # Leave space for QTextDocument margins, avoiding a spurious horizontal scrollbar.
            blocks.append('<table width="98%" cellspacing="0" cellpadding="7">'
                          '<tr bgcolor="' + COLORS['info_surface'] + '"><th align="left">Concepto</th>'
                          '<th align="right">Tempo</th><th align="right">PM</th><th align="right">Resultado</th></tr>')
        selected = field if field in ordered else (ordered[0] if ordered else None)
        for name in ordered:
            index = fields.index(name)
            minutes = row.sap_daily_minus_noise_minutes if name == "Control" else row.values_minutes.get(name)
            colors = comparison_colors(minutes, red=name in row.red_fields,
                                       suppressed=row.missing_source != "" or name in row.suppressed_fields)
            bg, fg = colors or (COLORS["background"].lstrip("#"), COLORS["text"].lstrip("#"))
            left, right, value, label = comparison_triplet(row, name)
            selected_color = COLORS['info_surface'] if name == selected else COLORS['surface']
            marker = " →" if name == selected else ""
            annotation = "<br><small>Valor directo</small>" if label == "Valor a revisar" else ""
            blocks.append(f'<tr bgcolor="{selected_color}"><td><a style="color:{COLORS["primary"]}" href="#concept{index}">{escape(name)}{marker}</a></td>'
                          f'<td align="right">{escape(left)}</td><td align="right">{escape(right)}</td>'
                          f'<td align="right" bgcolor="#{bg}" style="color:#{fg}"><b>{escape(value)}</b>{annotation}</td></tr>')
        if ordered:
            blocks.append('</table>')
        if selected:
            explanation = escape(calculation_text(row, selected)).replace("\n", "<br>")
            blocks.append(f'<h3>Cálculo de {escape(selected)}</h3><p>{explanation}</p>')
            if selected == "BOLSA (X%)" and row.section.upper().strip() in COMBINED_EXTRA_BOLSA_SECTIONS:
                blocks.append('<p>En esta fila, PM representa la suma de H. EXTRAS y BOLSA.</p>')
        self.browser.setHtml("".join(blocks))
        self.browser.verticalScrollBar().setValue(0)
