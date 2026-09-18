"""Home launcher with vertical tool cards and responsive internal columns."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                              QScrollArea, QSizePolicy, QVBoxLayout, QWidget)
from core.app_info import APP_VERSION
from services.update_service import UpdateService
from ui.theme import FINURA_LOGO, RODRIGUEZ_LOGO, ASSETS_DIR, HOME_LAYOUT


def label(text, name='mutedLabel'):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setObjectName(name)
    item.setWordWrap(True)
    item.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
    return item


class ToolCard(QFrame):
    def __init__(self, eyebrow, title, description, chips, needs, produces, button, shortcut, icon, open_tool, guide):
        super().__init__()
        self.setObjectName('homeToolCard')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.grid = QGridLayout(self)
        margin = HOME_LAYOUT['card_margin']
        self.grid.setContentsMargins(margin, margin, margin, margin)
        self.grid.setHorizontalSpacing(HOME_LAYOUT['gap'])
        self.grid.setVerticalSpacing(14)
        self.description = QWidget()
        description_layout = QHBoxLayout(self.description)
        description_layout.setContentsMargins(0, 0, 0, 0)
        description_layout.setSpacing(20)
        symbol = QLabel()
        symbol.setObjectName('homeToolIcon')
        symbol.setPixmap(QIcon(str(ASSETS_DIR / icon)).pixmap(42, 42))
        symbol.setAccessibleName(title)
        description_layout.addWidget(symbol, 0, Qt.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(8)
        words.addWidget(label(eyebrow, 'homeEyebrow'))
        words.addWidget(label(title, 'homeToolTitle'))
        words.addWidget(label(description))
        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        for text in chips:
            chip = label(text, 'homeChips')
            chip.setWordWrap(False)
            chip_row.addWidget(chip, 0, Qt.AlignLeft)
        chip_row.addStretch(1)
        words.addLayout(chip_row)
        description_layout.addLayout(words, 1)
        self.summary = QFrame()
        self.summary.setObjectName('homeToolSummary')
        summary_layout = QGridLayout(self.summary)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(14)
        summary_layout.addWidget(label('Necesitas', 'sectionLabel'), 0, 0)
        summary_layout.addWidget(label(needs), 0, 1)
        summary_layout.addWidget(label('Obtienes', 'sectionLabel'), 1, 0)
        summary_layout.addWidget(label(produces), 1, 1)
        summary_layout.setColumnStretch(1, 1)
        self.actions = QWidget()
        self.actions.setFixedWidth(HOME_LAYOUT['action_width'])
        actions = QVBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        self.open_button = QPushButton(button + '  →')
        self.open_button.setObjectName('primaryButton')
        self.open_button.setAccessibleName(button)
        self.open_button.setToolTip(button + ' (' + shortcut + ')')
        self.open_button.clicked.connect(open_tool)
        self.guide_button = QPushButton('Ver guía')
        self.guide_button.setAccessibleName('Ver guía de ' + title)
        self.guide_button.clicked.connect(guide)
        actions.addWidget(self.open_button)
        actions.addWidget(self.guide_button)
        key = label(shortcut)
        key.setAlignment(Qt.AlignRight)
        actions.addWidget(key)
        self._wide = None
        self.set_wide(True)

    def set_wide(self, wide):
        if self._wide == wide:
            return
        self._wide = wide
        for widget in (self.description, self.summary, self.actions):
            self.grid.removeWidget(widget)
        for column in range(3):
            self.grid.setColumnStretch(column, 0)
            self.grid.setColumnMinimumWidth(column, 0)
        if wide:
            self.grid.addWidget(self.description, 0, 0, Qt.AlignVCenter)
            self.grid.addWidget(self.summary, 0, 1, Qt.AlignVCenter)
            self.grid.addWidget(self.actions, 0, 2, Qt.AlignVCenter)
            for column, stretch in enumerate((6, 4, 0)):
                self.grid.setColumnStretch(column, stretch)
        else:
            self.grid.addWidget(self.description, 0, 0)
            self.grid.addWidget(self.summary, 1, 0)
            self.grid.addWidget(self.actions, 0, 1, 2, 1, Qt.AlignVCenter)
            self.grid.setColumnStretch(0, 1)


class HomePage(QWidget):
    open_phase1 = Signal()
    open_comparador = Signal()
    phase1_help = Signal()
    comparator_help = Signal()
    help_requested = Signal()
    updates_requested = Signal()
    news_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('homeSurface')
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll)
        shell = QWidget()
        shell.setObjectName('homeSurface')
        self.scroll.setWidget(shell)
        shell_layout = QVBoxLayout(shell)
        margin = HOME_LAYOUT['page_margin']
        shell_layout.setContentsMargins(margin, margin, margin, margin)
        centered = QHBoxLayout()
        centered.setContentsMargins(0, 0, 0, 0)
        self.content = QWidget()
        self.content.setMaximumWidth(HOME_LAYOUT['content_max_width'])
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        centered.addStretch(1)
        centered.addWidget(self.content, 100)
        centered.addStretch(1)
        shell_layout.addLayout(centered)
        # Leave spare room outside the group, not between its related controls.
        shell_layout.addStretch(1)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(18)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label('INICIO', 'homeEyebrow'))
        titles.addWidget(label('¿Qué necesitas hacer?', 'homeTitle'))
        titles.addWidget(label('Elige una herramienta para empezar. Las guías te acompañan en cada paso.'))
        heading.addLayout(titles, 1)
        self.logos = QWidget()
        logos = QHBoxLayout(self.logos)
        for path, width in ((RODRIGUEZ_LOGO, 120), (FINURA_LOGO, 90)):
            if path.exists():
                logo = QLabel()
                logo.setPixmap(QPixmap(str(path)).scaled(width, 45, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                logo.setAccessibleName(path.stem)
                logos.addWidget(logo)
        heading.addWidget(self.logos)
        self.content_layout.addLayout(heading)
        self.control_card = ToolCard('RECOPILAR PARTES', 'Control Tempo',
            'Reúne los datos de los partes de trabajo en un único Excel, con una auditoría del proceso.',
            ('Diario', 'Mensual 20–20'), 'Uno o varios partes Excel', 'Recopilación y auditoría',
            'Abrir Control Tempo', 'Alt + 1', 'home_control.svg', self.open_phase1.emit, self.phase1_help.emit)
        self.comparator_card = ToolCard('REVISAR DIFERENCIAS', 'Comparador de Tempo',
            'Contrasta Partes Mensuales y Tempo y localiza los trabajadores que necesitan revisión.',
            ('Por sección', 'Detalle por trabajador'), 'Partes Mensuales + Tempo, o una comparación .rrhh recibida',
            'Diferencias, incidencias y resultado para compartir', 'Abrir Comparador', 'Alt + 2',
            'home_compare.svg', self.open_comparador.emit, self.comparator_help.emit)
        self.content_layout.addWidget(self.control_card)
        self.content_layout.addWidget(self.comparator_card)
        help_card = QFrame()
        help_card.setObjectName('homeHelpCard')
        help_layout = QHBoxLayout(help_card)
        help_layout.setContentsMargins(22, 16, 22, 16)
        explanation = QVBoxLayout()
        explanation.addWidget(label('¿No sabes cuál elegir?', 'homeHelpTitle'))
        explanation.addWidget(label('Para reunir partes de trabajo, abre Control Tempo.\nPara contrastar datos o revisar una comparación recibida, abre Comparador de Tempo.'))
        help_layout.addLayout(explanation, 1)
        self.help_button = QPushButton('Abrir ayuda  F1')
        self.help_button.clicked.connect(self.help_requested.emit)
        help_layout.addWidget(self.help_button)
        self.content_layout.addWidget(help_card)
        footer = QHBoxLayout()
        edition = '' if UpdateService.is_installed_copy() else ' · Prueba local'
        footer.addWidget(label(f'Suite RRHH · v{APP_VERSION}{edition}'))
        self.news_button = QPushButton('Novedades')
        self.news_button.clicked.connect(self.news_requested.emit)
        footer.addWidget(self.news_button)
        footer.addStretch(1)
        self.update_status = label('')
        footer.addWidget(self.update_status)
        self.updates_button = QPushButton('Buscar actualizaciones')
        self.updates_button.clicked.connect(self.updates_requested.emit)
        footer.addWidget(self.updates_button)
        self.content_layout.addLayout(footer)
        controls = (self.control_card.open_button, self.control_card.guide_button,
                    self.comparator_card.open_button, self.comparator_card.guide_button,
                    self.help_button, self.news_button, self.updates_button)
        for first, second in zip(controls, controls[1:]):
            QWidget.setTabOrder(first, second)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available_width = min(self.width() - 2 * HOME_LAYOUT['page_margin'],
                              HOME_LAYOUT['content_max_width'])
        wide = available_width >= HOME_LAYOUT['wide_breakpoint']
        self.control_card.set_wide(wide)
        self.comparator_card.set_wide(wide)
        self.logos.setVisible(self.width() >= 1100)
