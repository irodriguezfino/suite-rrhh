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
                "Los dos Excel de origen se leen sin modificarlos. La comparación se hace por código Tempo, "
                "manteniendo el periodo que ya esté filtrado en el Excel de Partes Mensuales."
            ))
            steps = QHBoxLayout()
            steps.setSpacing(12)
            steps.addWidget(self._step_card("1", "Selecciona Partes Mensuales", "El Excel con la tabla dinámica y el periodo que quieres revisar."))
            steps.addWidget(self._step_card("2", "Selecciona Tempo", "El Excel Tempo de tiempos por trabajador, en formato .xls o .xlsx."))
            steps.addWidget(self._step_card("3", "Comprueba y revisa", "Se crean el informe principal y un Excel independiente de incidencias."))
            layout.addLayout(steps)
            layout.addWidget(self._callout(
                "Revisa sin salir de la aplicación",
                "La vista previa mantiene siempre el orden por sección y apellidos. Sección, código y trabajador permanecen fijos "
                "al desplazarte horizontalmente; puedes ajustar sus anchos. Combina sección, búsqueda por nombre o código (Ctrl+F) "
                "y motivo de revisión. Revisar ABSENT incluye también los absentismos en rojo cuya diferencia es cero. "
                "El filtro Incidencia ofrece los tipos presentes en el resultado completo y Sin incidencias cuando corresponda; "
                "si alguien tiene varias, podrás encontrarlo por cualquiera de ellas. Todos los filtros se combinan. "
                "El resumen de filtros activos explica qué estás viendo; Quitar filtros recupera todas las filas. "
                "Los recuentos de origen no cambian al buscar. Los filtros solo cambian la vista: no modifican el Excel completo ni sus cálculos.",
            ))
            layout.addWidget(self._callout(
                "Entiende el cálculo y recorre los trabajadores",
                "Pulsa Detalle del trabajador o Intro sobre la tabla. Verás una tabla compacta con cada concepto, Tempo, PM y Resultado; los controles directos "
                "en rojo se identifican como Valor directo. Selecciona el concepto para consultar su cálculo debajo y localizar su celda en la tabla principal. Primero aparecen los campos relevantes y el que hayas seleccionado. "
                "Ver todos los campos muestra el resto. Anterior y Siguiente recorren la lista filtrada sin alterar su orden. "
                "Cerrar o Esc devuelve el espacio a la tabla; el panel conserva el ancho que ajustes durante la sesión. "
                "Si necesitas más espacio, Ampliar abre una ventana grande; Esc la cierra y vuelve a la revisión. "
                "Si reduces la ventana, se cierra sin abrir nada inesperado; puedes abrirlo de nuevo como diálogo con el mismo botón.",
            ))
            layout.addWidget(self._callout(
                "Adapta la vista a tu forma de trabajar",
                "El resultado dedica casi toda la pantalla a la tabla y al detalle. La barra de archivos está plegada: en Vista puedes "
                "Mostrar archivos de origen, consultar las rutas o Cambiar archivos. "
                "El botón Nueva comparación, al pie de la tabla, vuelve a la selección inicial y limpia archivos seleccionados, "
                "filtros y vista previa sin cerrar la aplicación. No borra los informes guardados ni las carpetas recordadas. "
                "En Vista también puedes activar Filas compactas para ver más trabajadores sin reducir la letra, o dejar las filas cómodas. "
                "Restablecer anchos recupera el tamaño inicial de las columnas. Lectura accesible usa una única tabla nativa sin "
                "columnas congeladas, para evitar duplicados al usar lectores de pantalla. La densidad y este modo se recuerdan. "
                "Ver rutas permite leer y copiar las rutas completas con el teclado. Registro del proceso contiene los detalles técnicos, "
                "no el desglose de un trabajador. El signo negativo es −, mientras — indica que no se muestra una comparación.",
            ))
            layout.addWidget(self._callout(
                "Continúa desde tus carpetas habituales",
                "La aplicación recuerda por separado las carpetas de Partes Mensuales, Tempo y resultados. "
                "Al volver a abrirla, cada selector empieza en su última carpeta. Limpiar vacía la comparación, "
                "pero conserva estas ubicaciones. Selecciona los archivos del periodo que quieras comprobar.",
            ))
            layout.addWidget(self._callout(
                "Los archivos originales están protegidos",
                "La aplicación trabaja con copias temporales y nunca sobrescribe Partes Mensuales ni el Excel Tempo.",
                "success",
            ))
            layout.addWidget(self._title("La idea clave"))
            formula = QFrame()
            formula.setObjectName("helpFormulaCard")
            formula_layout = QHBoxLayout(formula)
            formula_layout.setContentsMargins(18, 16, 18, 16)
            formula_layout.setSpacing(12)
            for text, style in (
                ("Tiempo Tempo", "helpFormulaSource"),
                ("−", "helpFormulaOperator"),
                ("Tiempo de Partes Mensuales", "helpFormulaSource"),
                ("=", "helpFormulaOperator"),
                ("Diferencia", "helpFormulaResult"),
            ):
                formula_layout.addWidget(self._label(text, style), 0, Qt.AlignCenter)
            layout.addWidget(formula)
            layout.addWidget(self._callout(
                "Cómo interpretar el signo",
                "Ejemplo: +0:30 significa que Tempo tiene 30 minutos más. −0:30 significa que Partes Mensuales tiene 30 minutos más.",
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
                ("Código SAP", "Identificador del trabajador en Tempo, también en el listado final de ausentes.", "80700"),
                ("Trabajador", "Nombre asociado al código Tempo comparado.", "PÉREZ GARCÍA ANA"),
                ("Incidencias", "Marcajes, ausencias u origen donde falta el trabajador. Sin incidencias: −.", "No aparece en Tempo"),
                ("Trab. Día Tempo", "Total Tempo de Trab. Dia. No es una diferencia.", "8:00"),
                ("Control", "Trab. Día Tempo − RUIDO PM. Se revisa si supera un minuto.", "8:00 − 7:45 = +0:15"),
                ("Δ H. EXTRAS", "1016-HE Tempo − H. EXTRAS PM.", "1:30 − 1:00 = +0:30"),
                ("Δ HFJ (15%)", "1129-HE15% Tempo − HFJ PM.", "0:00 − 0:20 = −0:20"),
                ("Δ BOLSA (X%)", "1166-HE35% Tempo − BOLSA PM.", "2:00 − 1:45 = +0:15"),
                ("Δ NOCTUR", "1014-HNOC Tempo − NOCTUR PM, salvo ADMON y RRHH.", "4:00 − 3:30 = +0:30"),
                ("Δ PENOS", "1146-PPEN Tempo − PENOS PM.", "0:00 − 0:30 = −0:30"),
                ("Δ RUIDO", "1153-PRUI Tempo − RUIDO PM, salvo control rojo.", "0:30 − 0:45 = −0:15"),
                ("ABSENT", "1052-HDESC Tempo − ABSENT PM, solo si existe absentismo.", "8:00 − 8:00 = 0:00"),
            )
            for row, values in enumerate(rows, start=1):
                for column, value in enumerate(values):
                    grid.addWidget(self._label(value, "helpGridCell"), row, column)
            grid.setColumnStretch(0, 2)
            grid.setColumnStretch(1, 5)
            grid.setColumnStretch(2, 3)
            layout.addLayout(grid)
            layout.addWidget(self._title("Un guion y un cero significan cosas distintas"))
            examples = QHBoxLayout()
            examples.setSpacing(12)
            examples.addWidget(self._step_card("1", "Ambos tiempos a cero", "Tempo 0:00 − PM 0:00 → −. No hay tiempo en ninguno de los dos orígenes."), 1)
            examples.addWidget(self._step_card("2", "Tiempos iguales con datos", "Tempo 8:00 − PM 8:00 → 0:00. Hay tiempo y coincide; se conserva si la fila aparece por otro motivo."), 1)
            examples.addWidget(self._step_card("3", "Solo uno tiene tiempo", "Tempo 0:00 − PM 0:30 → −0:30. Se muestra la diferencia con su signo."), 1)
            layout.addLayout(examples)
            layout.addWidget(self._label(
                "Esta regla se aplica a todas las diferencias, incluido Control y ABSENT. Trab. Día Tempo es un total, "
                "por lo que puede mostrar 0:00. En el listado final de trabajadores sin correspondencia, todos los tiempos son guiones."
            ))
            layout.addWidget(self._callout(
                "Absentismo sin datos",
                "Cuando tanto Tempo como Partes Mensuales tienen 0:00 de absentismo, ABSENT muestra −. Si existe en cualquiera de los dos, se muestra la diferencia, incluso cuando sea 0:00.",
                "warning",
            ))

        return self._scroll_tab(build)

    def _build_rules_tab(self) -> QScrollArea:
        def build(layout: QVBoxLayout) -> None:
            layout.addWidget(self._title("Reglas que cambian la lectura habitual"))
            layout.addWidget(self._callout(
                "ML, MS, MC y MV: extras y bolsa se revisan juntas",
                "Δ H. EXTRAS muestra −. Δ BOLSA (X%) calcula 1166-HE35% Tempo − (H. EXTRAS + BOLSA PM). "
                "Ejemplo: 2:00 − (0:45 + 1:00) = +0:15.",
            ))
            layout.addWidget(self._callout(
                "Ruido no permitido en determinadas secciones",
                "En ADMON, C (Congelado), CAL, COMP, X (Expediciones), RRHH, RT, SV, SVC, TIC y MTO, Tempo no debería tener 1153-PRUI. "
                "Si Tempo tiene 0:00, Δ RUIDO muestra −, aunque PM tenga tiempo. Si Tempo tiene un valor distinto de cero, "
                "se muestra ese valor directamente en rojo. Control sigue comparando Trab. Día Tempo − RUIDO PM.",
                "danger",
            ))
            layout.addWidget(self._callout(
                "Nocturnidad no permitida en ADMON y RRHH",
                "Si 1014-HNOC de Tempo es 0:00, Δ NOCTUR muestra −, aunque PM tenga nocturnidad. Ese tiempo de PM "
                "no incluye por sí solo al trabajador. Si Tempo contiene nocturnidad, se muestra su valor directamente en rojo.",
                "danger",
            ))
            layout.addWidget(self._callout(
                "Penosidad",
                "Δ PENOS se calcula siempre como 1146-PPEN Tempo − PENOS PM. Verde si es negativa, "
                "amarillo si es positiva y sin resaltado si es cero.",
                "warning",
            ))
            layout.addWidget(self._callout(
                "Cómo leer los colores",
                "Verde: diferencia negativa (Tempo tiene menos tiempo que PM). Amarillo: diferencia positiva (Tempo tiene más). "
                "Rojo: controles especiales y absentismo, con prioridad aunque el resultado sea negativo o cero. "
                "Los ceros normales, los guiones y el texto de Incidencias no llevan resaltado. "
                "El color se aplica también a Control y a diferencias de un minuto si la fila aparece por otro motivo; "
                "la tolerancia para incluir trabajadores sigue siendo superior a un minuto.",
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
                "✓ Una diferencia de Control superior a un minuto: Trab. Día Tempo − RUIDO PM.",
                "✓ Un control directo Tempo mostrado en rojo: ruido o nocturnidad.",
                "✓ Absentismo en Tempo o en Partes Mensuales, aunque la diferencia final sea 0:00.",
                "✓ Falta de fichaje de entrada o de salida.",
                "✓ Solo aparece en uno de los dos orígenes: se añade al listado final, con todos los tiempos en −.",
            ):
                checks_layout.addWidget(self._label(text, "helpChecklistItem"))
            layout.addWidget(checks)
            layout.addWidget(self._callout(
                "Margen de un minuto",
                "Una diferencia de 0:01 o menor no incluye por sí sola al trabajador. Por ejemplo, Tempo 8:00 y Partes Mensuales 7:59 no dispara una revisión.",
            ))
            layout.addWidget(self._callout(
                "Recuentos por sección: antes de filtrar diferencias",
                "Cada sección indica cuántos trabajadores aparecen en Partes Mensuales y cuántos se encuentran también "
                "en Tempo mediante un código verificado. Incluye a quienes no tienen diferencias. Ejemplo: ML · Partes Mensuales: 25 · "
                "Tempo: 24 indica que falta una correspondencia en Tempo. Los duplicados del mismo código no aumentan el recuento. "
                "También se muestran las secciones sin diferencias.",
            ))
            layout.addWidget(self._callout(
                "Al final: trabajadores que faltan en un origen",
                "Si solo está en PM, Incidencias indica «No aparece en Tempo» y su sección. Si solo está en Tempo, "
                "indica «No aparece en Partes Mensuales» y «Sección: Sin asignar». Todos sus tiempos y diferencias son −: "
                "no se calcula contra un trabajador ausente. Puedes verlos juntos con el filtro «Solo en un origen».",
                "warning",
            ))
            layout.addWidget(self._callout(
                "Un trabajador puede cambiar de sección",
                "Un mismo código en varias secciones sigue siendo un único trabajador. Se compara una sola vez y se "
                "agrupa en la última sección registrada dentro del periodo seleccionado en PM. Por ejemplo: 80700, antes en C "
                "y el 10/09 en X, se agrupa en X al revisar el 10/09. El Excel de incidencias documenta el cambio. Si el filtro "
                "de fecha o la última sección no permiten resolverlo con seguridad, se muestra «Sección pendiente de verificar» "
                "y se comparan sus tiempos por código. No se marca como ausente por cambiar de sección.",
                "warning",
            ))
            layout.addWidget(self._callout(
                "Qué puede y qué no puede decir el recuento",
                "Los trabajadores que solo están en Tempo no se suman a una sección, porque ese archivo no permite asignarla "
                "con seguridad. Revisa siempre el listado final, incluso si los recuentos de una sección coinciden. Una identidad "
                "ambigua queda documentada en el Excel de incidencias; no se inventa una correspondencia.",
            ))
            layout.addWidget(self._callout(
                "Dos Excel de salida",
                "El informe principal contiene las diferencias por sección y, al final, las personas que faltan en un origen. "
                "El Excel de incidencias conserva los valores originales y los datos de apoyo: códigos no encontrados, "
                "identidades no verificables, duplicados y marcajes detectados. Usa el filtro de sección y la búsqueda por nombre "
                "o código para revisar la vista previa. Los recuentos de origen no cambian al buscar un trabajador.",
                "success",
            ))

        return self._scroll_tab(build)
