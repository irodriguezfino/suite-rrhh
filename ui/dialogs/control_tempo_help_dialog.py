"""Guía visual y contextual para Control Tempo."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ControlTempoHelpDialog(QDialog):
    """Presenta el flujo de Control Tempo con explicaciones breves y contextuales."""

    def __init__(
        self,
        file_count: int,
        selected_date: date,
        is_monthly: bool,
        output_path: Path | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._file_count = file_count
        self._selected_date = selected_date
        self._is_monthly = is_monthly
        self._output_path = output_path
        self.setObjectName("controlTempoHelpDialog")
        self.setWindowTitle("Guía de Control Tempo")
        self.setModal(True)
        self.setMinimumSize(820, 580)
        self.resize(1020, 710)
        self.setAccessibleName("Guía de uso de Control Tempo")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("helpHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(5)
        title = QLabel("Guía rápida de Control Tempo")
        title.setObjectName("helpHeroTitle")
        hero_layout.addWidget(title)
        subtitle = QLabel(
            "Prepara partes Excel, define el periodo de consulta y genera una recopilación auditada "
            "sin modificar los archivos originales."
        )
        subtitle.setObjectName("helpHeroSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)
        layout.addWidget(hero)

        tabs = QTabWidget()
        tabs.setObjectName("comparadorHelpTabs")
        tabs.setAccessibleName("Secciones de ayuda de Control Tempo")
        tabs.addTab(self._build_setup_tab(), "1. Preparar")
        tabs.addTab(self._build_period_tab(), "2. Fecha y modo")
        tabs.addTab(self._build_result_tab(), "3. Resultado")
        tabs.addTab(self._build_safe_work_tab(), "4. Trabajo seguro")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.setAccessibleName("Cerrar la guía")
        layout.addWidget(buttons)

    def _scroll_tab(self, builder) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("helpTabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 16, 10, 12)
        layout.setSpacing(14)
        builder(layout)
        layout.addStretch(1)
        area.setWidget(content)
        return area

    @staticmethod
    def _label(text: str, object_name: str = "helpBody") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _title(text: str) -> QLabel:
        return ControlTempoHelpDialog._label(text, "helpSectionTitle")

    def _callout(self, title: str, text: str, tone: str = "info") -> QFrame:
        card = QFrame()
        card.setObjectName(f"helpCallout{tone.title()}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 13)
        card_layout.setSpacing(4)
        card_layout.addWidget(self._label(title, "helpCalloutTitle"))
        card_layout.addWidget(self._label(text, "helpCalloutText"))
        return card

    def _step_card(self, number: str, title: str, text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("helpStepCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(5)
        badge = self._label(number, "helpStepNumber")
        card_layout.addWidget(badge, 0, Qt.AlignLeft)
        card_layout.addWidget(self._label(title, "helpCardTitle"))
        card_layout.addWidget(self._label(text, "helpCardText"))
        return card

    def _state_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("helpStateCard")
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(7)
        grid.addWidget(self._label("Estado actual", "helpCardTitle"), 0, 0, 1, 2)
        values = (
            ("Partes", f"{self._file_count} seleccionado(s)"),
            ("Fecha", self._selected_date.strftime("%d/%m/%Y")),
            ("Modo", "Mensual 20–20" if self._is_monthly else "Diario"),
            ("Salida", self._output_path.name if self._output_path else "Aún sin definir"),
        )
        for row, (label, value) in enumerate(values, start=1):
            grid.addWidget(self._label(label, "helpStateKey"), row, 0)
            grid.addWidget(self._label(value, "helpStateValue"), row, 1)
        grid.setColumnStretch(1, 1)
        return card

    def _build_setup_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Prepara una recopilación en cuatro pasos"))
            layout.addWidget(self._label(
                "Puedes añadir uno o varios partes Excel. La aplicación procesa los archivos sin alterar sus originales "
                "y genera un único Excel final en la ruta que elijas."
            ))
            steps = QHBoxLayout()
            steps.setSpacing(12)
            steps.addWidget(self._step_card("1", "Añade partes", "Pulsa Añadir archivos o arrastra los Excel a la ventana."))
            steps.addWidget(self._step_card("2", "Elige fecha", "Selecciona la fecha que debe regir la consulta."))
            steps.addWidget(self._step_card("3", "Elige modo", "Usa Diario o Mensual 20–20 según el resultado necesario."))
            steps.addWidget(self._step_card("4", "Genera", "Indica dónde guardar el Excel y pulsa Generar Control Tempo."))
            layout.addLayout(steps)
            layout.addWidget(self._state_card())
            layout.addWidget(self._callout(
                "Archivos de red y selección múltiple",
                "Puedes elegir partes desde distintas carpetas o ubicaciones de red. Antes de generar, comprueba que todas las rutas sigan disponibles.",
            ))
            layout.addWidget(self._callout(
                "Salida segura",
                "Elige un nombre nuevo o cierra el Excel de salida si ya existe. Así se evita que Windows o Excel bloqueen el archivo durante la generación.",
                "warning",
            ))

        return self._scroll_tab(build)

    def _build_period_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("La fecha define qué datos se recopilan"))
            layout.addWidget(self._callout(
                "Modo Diario",
                "Se toman los datos correspondientes únicamente a la fecha seleccionada. Ejemplo: al elegir 06/08/2026, se consulta solo el día 06/08/2026.",
            ))
            layout.addWidget(self._callout(
                "Modo Mensual 20–20",
                "Conserva el tramo del ciclo que termina en la fecha elegida. Si eliges una fecha anterior al día 21, toma desde el día 21 del mes anterior; "
                "si eliges una fecha desde el día 21, toma desde ese día 21 del mismo mes.",
                "success",
            ))
            examples = QFrame()
            examples.setObjectName("helpChecklistCard")
            examples_layout = QVBoxLayout(examples)
            examples_layout.setContentsMargins(18, 16, 18, 16)
            examples_layout.setSpacing(8)
            examples_layout.addWidget(self._label("Ejemplos del ciclo 20–20", "helpCardTitle"))
            examples_layout.addWidget(self._label("• Fecha 12/06/2026 → periodo desde 21/05/2026 hasta 12/06/2026; bloque CONTROL de JUNIO.", "helpChecklistItem"))
            examples_layout.addWidget(self._label("• Fecha 29/07/2026 → periodo desde 21/07/2026 hasta 29/07/2026; bloque CONTROL de AGOSTO.", "helpChecklistItem"))
            layout.addWidget(examples)
            layout.addWidget(self._callout(
                "Trabajadores incluidos",
                "La fecha también se usa para comprobar altas y bajas. Se conservan los trabajadores activos en esa fecha según la información del parte.",
                "warning",
            ))

        return self._scroll_tab(build)

    def _build_result_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Qué ocurre al generar"))
            layout.addWidget(self._label(
                "Control Tempo valida primero que los libros tengan las hojas necesarias y después procesa los partes en paralelo para reducir el tiempo de espera."
            ))
            result_cards = QHBoxLayout()
            result_cards.setSpacing(12)
            result_cards.addWidget(self._step_card("A", "Excel final", "Una recopilación única con los trabajadores y datos correspondientes al periodo elegido."))
            result_cards.addWidget(self._step_card("B", "Centro de actividad", "Muestra el archivo que se está procesando, el avance, el tiempo transcurrido y el total exportado."))
            result_cards.addWidget(self._step_card("C", "Auditoría", "Permite consultar el detalle técnico por parte si necesitas comprobar un resultado o informar de un error."))
            layout.addLayout(result_cards)
            layout.addWidget(self._callout(
                "Tras terminar",
                "Usa Abrir Excel generado para revisar el resultado, Abrir carpeta para localizarlo o Ver auditoría si necesitas el detalle de la ejecución.",
                "success",
            ))
            layout.addWidget(self._callout(
                "Si un parte falla",
                "No se genera un Excel final incompleto. La aplicación indica el archivo afectado y permite consultar los detalles técnicos para corregirlo con seguridad.",
                "danger",
            ))

        return self._scroll_tab(build)

    def _build_safe_work_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Trabaja de forma segura y rápida"))
            checks = QFrame()
            checks.setObjectName("helpChecklistCard")
            checks_layout = QVBoxLayout(checks)
            checks_layout.setContentsMargins(18, 16, 18, 16)
            checks_layout.setSpacing(9)
            for text in (
                "✓ Cierra el Excel final antes de volver a generar sobre el mismo archivo.",
                "✓ Espera a que termine el proceso antes de apagar el equipo o desconectar una ruta de red.",
                "✓ Si necesitas detenerlo, usa Cancelar proceso: no se dejará un resultado final a medias.",
                "✓ Si una ruta de red no está disponible, quita ese parte o restablece la conexión antes de generar.",
                "✓ Pulsa Restablecer para iniciar otra recopilación sin conservar la configuración anterior.",
            ):
                checks_layout.addWidget(self._label(text, "helpChecklistItem"))
            layout.addWidget(checks)
            layout.addWidget(self._callout(
                "Atajos útiles",
                "Ctrl+O añade partes · Ctrl+S elige la salida · Ctrl+R inicia la generación · Ctrl+D abre la auditoría · F1 abre esta guía.",
            ))
            layout.addWidget(self._callout(
                "La ventana sigue disponible",
                "El procesamiento se ejecuta fuera de la interfaz. Puedes consultar el progreso, cancelar o esperar sin que la ventana quede bloqueada.",
                "success",
            ))

        return self._scroll_tab(build)
