"""Punto de entrada único de la interfaz PySide6."""

from __future__ import annotations

import multiprocessing
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_application_style


def main() -> int:
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    app.setApplicationName("Suite RRHH")
    app.setOrganizationName("Grupo Vall")
    app.setFont(QFont("Segoe UI", 11))
    apply_application_style(app)
    window = MainWindow()
    # Ventana maximizada, conservando la barra de título y controles nativos
    # de Windows para minimizar, restaurar/maximizar y cerrar.
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
