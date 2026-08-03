from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


class ErrorDialog(QDialog):
    def __init__(self, message: str, detail: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("No se pudo generar la recopilación")
        self.setMinimumSize(640, 360)
        self.setAccessibleName("Error durante la recopilación")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        summary = QLabel(f"<b>No se pudo completar el proceso.</b><br><br>{message}<br><br>Revisa los archivos, la fecha y que el Excel de salida no esté abierto.")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addWidget(QLabel("Detalle técnico (para soporte):"))
        text = QPlainTextEdit(detail)
        text.setReadOnly(True)
        text.setAccessibleName("Detalle técnico del error")
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
