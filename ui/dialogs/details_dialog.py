from __future__ import annotations

from PySide6.QtGui import QTextCursor
from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout


class DetailsDialog(QDialog):
    def __init__(self, details: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auditoría y detalles técnicos")
        self.setMinimumSize(720, 440)
        self.resize(860, 560)
        self.setAccessibleName("Auditoría y detalles del proceso")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Auditoría y detalles técnicos"))

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Buscar:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Texto a buscar en el registro")
        self.search.setAccessibleName("Buscar en detalles")
        self.search.returnPressed.connect(self.find_next)
        search_row.addWidget(self.search, 1)
        find_button = QPushButton("Buscar siguiente")
        find_button.clicked.connect(self.find_next)
        search_row.addWidget(find_button)
        layout.addLayout(search_row)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText("\n".join(details))
        self.text.setAccessibleName("Registro técnico del proceso")
        layout.addWidget(self.text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        export_button = buttons.addButton("Exportar detalles…", QDialogButtonBox.ActionRole)
        export_button.clicked.connect(self.export_details)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def find_next(self) -> None:
        query = self.search.text().strip()
        if not query:
            return
        document = self.text.document()
        cursor = document.find(query, self.text.textCursor())
        if cursor.isNull():
            cursor = document.find(query, QTextCursor(document))
        if not cursor.isNull():
            self.text.setTextCursor(cursor)
            self.text.ensureCursorVisible()

    def export_details(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Guardar detalles de auditoría", "auditoria_control_tempo.txt", "Texto (*.txt)")
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")
        try:
            path.write_text(self.text.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo exportar", f"No se pudieron guardar los detalles.\n\n{exc}")
        else:
            QMessageBox.information(self, "Detalles exportados", f"La auditoría se ha guardado en:\n{path}")
