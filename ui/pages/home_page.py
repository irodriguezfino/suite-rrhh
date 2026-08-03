from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.theme import FINURA_LOGO, RODRIGUEZ_LOGO


class HomePage(QWidget):
    open_phase1 = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 42, 42, 42)
        layout.setSpacing(24)

        title_row = QHBoxLayout()
        title = QLabel("Suite RRHH")
        title.setObjectName("homeTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        for path, width, height in ((RODRIGUEZ_LOGO, 150, 58), (FINURA_LOGO, 110, 46)):
            if path.exists():
                logo = QLabel()
                logo.setAccessibleName(path.stem.replace("_", " "))
                logo.setPixmap(QPixmap(str(path)).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                title_row.addWidget(logo)
        layout.addLayout(title_row)
        subtitle = QLabel("Herramientas de gestión de recursos humanos")
        subtitle.setObjectName("mutedLabel")
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(10)
        heading = QLabel("Control Tempo · Recopilación de datos Excel")
        heading.setObjectName("homeHeading")
        card_layout.addWidget(heading)
        text = QLabel("Procesa partes Excel, aplica los modos Diario o Mensual 20–20 y genera una recopilación auditada.")
        text.setWordWrap(True)
        text.setObjectName("mutedLabel")
        card_layout.addWidget(text)
        row = QHBoxLayout()
        open_button = QPushButton("Abrir Control Tempo")
        open_button.setObjectName("primaryButton")
        open_button.setAccessibleName("Abrir Control Tempo")
        open_button.clicked.connect(self.open_phase1.emit)
        row.addWidget(open_button)
        row.addStretch(1)
        card_layout.addLayout(row)
        layout.addWidget(card)
        layout.addStretch(1)
