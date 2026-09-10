"""Guía visual y contextual para el informe del Comparador de Tempo."""

from __future__ import annotations

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


class ComparadorTempoHelpDialog(QDialog):
    """Explica el flujo y las reglas del comparador sin requerir conocimiento técnico."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("comparadorHelpDialog")
        self.setWindowTitle("Guía del Comparador de Tempo")
        self.setModal(True)
        self.setMinimumSize(820, 580)
        self.resize(1020, 710)
        self.setAccessibleName("Guía del informe del Comparador de Tempo")
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
        title = QLabel("Guía rápida del Comparador de Tempo")
        title.setObjectName("helpHeroTitle")
        hero_layout.addWidget(title)
        subtitle = QLabel(
            "Consulta cómo se seleccionan los trabajadores, qué significa cada valor "
            "y cuándo una cifra requiere revisión."
        )
        subtitle.setObjectName("helpHeroSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)
        layout.addWidget(hero)

        tabs = QTabWidget()
        tabs.setObjectName("comparadorHelpTabs")
        tabs.setAccessibleName("Secciones de ayuda del Comparador de Tempo")
        tabs.addTab(self._build_process_tab(), "1. Proceso")
        tabs.addTab(self._build_columns_tab(), "2. Leer el informe")
        tabs.addTab(self._build_rules_tab(), "3. Casos especiales")
        tabs.addTab(self._build_review_tab(), "4. Cuándo revisar")
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
        return ComparadorTempoHelpDialog._label(text, "helpSectionTitle")

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

    def _build_process_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("El proceso, en tres pasos"))
            layout.addWidget(self._label(
                "Los dos Excel de origen se leen sin modificarlos. La comparación se hace por código SAP, "
                "manteniendo el periodo que ya esté filtrado en el Excel de Acumulado."
            ))
            steps = QHBoxLayout()
            steps.setSpacing(12)
            steps.addWidget(self._step_card("1", "Selecciona Acumulado", "El Excel con la tabla dinámica y el periodo que quieres revisar."))
            steps.addWidget(self._step_card("2", "Selecciona Tempo SAP", "El Excel SAP de tiempos por trabajador, en formato .xls o .xlsx."))
            steps.addWidget(self._step_card("3", "Comprueba y revisa", "Se crean el informe principal y un Excel independiente de incidencias."))
            layout.addLayout(steps)
            layout.addWidget(self._callout(
                "Los archivos originales están protegidos",
                "La aplicación trabaja con copias temporales y nunca sobrescribe el Acumulado ni el Excel Tempo SAP.",
                "success",
            ))
            layout.addWidget(self._title("La idea clave"))
            formula = QFrame()
            formula.setObjectName("helpFormulaCard")
            formula_layout = QHBoxLayout(formula)
            formula_layout.setContentsMargins(18, 16, 18, 16)
            formula_layout.setSpacing(12)
            for text, style in (
                ("Tiempo SAP", "helpFormulaSource"),
                ("−", "helpFormulaOperator"),
                ("Tiempo del Acumulado", "helpFormulaSource"),
                ("=", "helpFormulaOperator"),
                ("Diferencia", "helpFormulaResult"),
            ):
                formula_layout.addWidget(self._label(text, style), 0, Qt.AlignCenter)
            layout.addWidget(formula)
            layout.addWidget(self._callout(
                "Cómo interpretar el signo",
                "Ejemplo: +0:30 significa que SAP tiene 30 minutos más. −0:30 significa que el Acumulado tiene 30 minutos más.",
            ))

        return self._scroll_tab(build)

    def _build_columns_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Qué muestra cada columna"))
            layout.addWidget(self._label(
                "Las columnas que empiezan por Δ son diferencias. El informe enseña todos los valores de una fila "
                "para facilitar la revisión, aunque solo una de las columnas haya provocado su inclusión."
            ))
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(7)
            headers = ("Columna", "Cálculo o significado", "Ejemplo")
            for column, text in enumerate(headers):
                grid.addWidget(self._label(text, "helpGridHeader"), 0, column)
            rows = (
                ("Trabajador", "Nombre asociado al código SAP comparado.", "PÉREZ GARCÍA ANA"),
                ("Incidencias", "Falta de fichaje de entrada o salida; si no existe, muestra −.", "Falta fichaje de salida"),
                ("Trab. Día SAP", "Total SAP de Trab. Dia. No es una diferencia.", "8:00"),
                ("Δ Trab. Día − RUIDO", "Trab. Dia SAP − RUIDO del Acumulado.", "8:00 − 7:45 = +0:15"),
                ("Δ H. EXTRAS", "1016-HE SAP − H. EXTRAS Acumulado.", "1:30 − 1:00 = +0:30"),
                ("Δ HFJ (15%)", "1166-HE30% SAP − HFJ Acumulado.", "0:00 − 0:20 = −0:20"),
                ("Δ BOLSA (X%)", "1166-HE35% SAP − BOLSA Acumulado.", "2:00 − 1:45 = +0:15"),
                ("Δ NOCTUR", "1014-HNOC SAP − NOCTUR Acumulado.", "4:00 − 3:30 = +0:30"),
                ("Δ PENOS", "1146-PPEN SAP − PENOS Acumulado, salvo control rojo.", "0:00 − 0:30 = −0:30"),
                ("Δ RUIDO", "1153-PRUI SAP − RUIDO Acumulado, salvo control rojo.", "0:30 − 0:45 = −0:15"),
                ("ABSENT", "1052-HDESC SAP − ABSENT Acumulado, solo si existe absentismo.", "8:00 − 8:00 = 0:00"),
            )
            for row, values in enumerate(rows, start=1):
                for column, value in enumerate(values):
                    grid.addWidget(self._label(value, "helpGridCell"), row, column)
            grid.setColumnStretch(0, 2)
            grid.setColumnStretch(1, 5)
            grid.setColumnStretch(2, 3)
            layout.addLayout(grid)
            layout.addWidget(self._callout(
                "Absentismo sin datos",
                "Cuando tanto SAP como el Acumulado tienen 0:00 de absentismo, ABSENT muestra −. Si existe en cualquiera de los dos, se muestra la diferencia, incluso cuando sea 0:00.",
                "warning",
            ))

        return self._scroll_tab(build)

    def _build_rules_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Reglas que cambian la lectura habitual"))
            layout.addWidget(self._callout(
                "ML, MS, MC y MV: extras y bolsa se revisan juntas",
                "Δ H. EXTRAS muestra −. Δ BOLSA (X%) calcula 1166-HE35% SAP − (H. EXTRAS + BOLSA del Acumulado). "
                "Ejemplo: 2:00 − (0:45 + 1:00) = +0:15.",
            ))
            layout.addWidget(self._callout(
                "Ruido no permitido en determinadas secciones",
                "En ADMON, CONG, CAL, COMP, EXP, RRHH, RT, SV, SVC, TIC y MTO, SAP no debería tener 1153-PRUI. "
                "Si lo tiene, Δ RUIDO muestra directamente el valor SAP en rojo para revisarlo.",
                "danger",
            ))
            layout.addWidget(self._callout(
                "Nocturnidad no permitida en ADMON y RRHH",
                "Si SAP contiene 1014-HNOC en esas secciones, Δ NOCTUR muestra directamente ese valor en rojo.",
                "danger",
            ))
            layout.addWidget(self._callout(
                "Penosidad en SAP",
                "Si SAP contiene 1146-PPEN en cualquier sección, Δ PENOS muestra directamente ese valor en rojo. "
                "Si SAP está a cero, la columna vuelve a mostrar la diferencia normal con el Acumulado.",
                "danger",
            ))
            layout.addWidget(self._callout(
                "Rojo no siempre significa una diferencia",
                "El rojo identifica un control directo de SAP o un absentismo existente. El amarillo identifica una diferencia normal que supera el margen admitido.",
                "warning",
            ))

        return self._scroll_tab(build)

    def _build_review_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Cuándo aparece un trabajador en el informe"))
            layout.addWidget(self._label(
                "Se muestra una fila cuando hay algo que merece revisión. Esto evita imprimir trabajadores sin diferencias relevantes."
            ))
            checks = QFrame()
            checks.setObjectName("helpChecklistCard")
            checks_layout = QVBoxLayout(checks)
            checks_layout.setContentsMargins(18, 16, 18, 16)
            checks_layout.setSpacing(9)
            for text in (
                "✓ Una diferencia normal superior a un minuto.",
                "✓ Un control directo SAP mostrado en rojo: ruido, nocturnidad o penosidad.",
                "✓ Absentismo en SAP o en el Acumulado, aunque la diferencia final sea 0:00.",
                "✓ Falta de fichaje de entrada o de salida.",
            ):
                checks_layout.addWidget(self._label(text, "helpChecklistItem"))
            layout.addWidget(checks)
            layout.addWidget(self._callout(
                "Margen de un minuto",
                "Una diferencia de 0:01 o menor no incluye por sí sola al trabajador. Por ejemplo, SAP 8:00 y Acumulado 7:59 no dispara una revisión.",
            ))
            layout.addWidget(self._callout(
                "Dos Excel de salida",
                "El informe principal contiene los trabajadores a revisar. El Excel de incidencias conserva además datos de apoyo: códigos no encontrados, duplicados y marcajes detectados.",
                "success",
            ))

        return self._scroll_tab(build)
