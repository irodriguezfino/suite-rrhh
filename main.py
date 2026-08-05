"""Punto de entrada único de la interfaz PySide6."""

from __future__ import annotations

import multiprocessing
import sys
import traceback

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from services.diagnostics import RunDiagnostics
from ui.main_window import MainWindow
from ui.theme import apply_application_style


def _install_exception_diagnostics() -> None:
    """Conserva el detalle de excepciones no controladas sin interferir con Qt."""
    previous_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        diagnostics = RunDiagnostics("application")
        diagnostics.record(
            "uncaught_exception",
            exception_type=getattr(exc_type, "__name__", str(exc_type)),
            error=str(exc_value),
            traceback="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def main() -> int:
    multiprocessing.freeze_support()
    _install_exception_diagnostics()
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
