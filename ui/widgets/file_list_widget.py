from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget


class FileTable(QTableWidget):
    files_dropped = Signal(list)
    delete_pressed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(0, 2, parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setHorizontalHeaderLabels(["Archivo", "Ubicación"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setDefaultSectionSize(260)
        self.setAccessibleName("Archivos Excel seleccionados")
        self.setAccessibleDescription("Lista de archivos de entrada. Usa Suprimir para quitar el archivo seleccionado.")

    def dragEnterEvent(self, event) -> None:
        if self._has_local_urls(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if self._has_local_urls(event):
            self.setProperty("dropActive", True)
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dropActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.setProperty("dropActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

    @staticmethod
    def _has_local_urls(event) -> bool:
        return event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls())

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class FileListWidget(QWidget):
    files_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._files: list[Path] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        info = QLabel("Añade partes Excel o arrástralos aquí. Puedes eliminar elementos individualmente.")
        info.setObjectName("mutedLabel")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = FileTable()
        self.table.files_dropped.connect(self.add_files)
        self.table.delete_pressed.connect(self.remove_selected)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.setMinimumHeight(150)
        layout.addWidget(self.table)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Añadir partes…")
        self.add_button.setToolTip("Ctrl+O")
        self.remove_button = QPushButton("Quitar seleccionados")
        self.remove_button.setEnabled(False)
        self.clear_button = QPushButton("Limpiar lista")
        self.clear_button.setEnabled(False)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear)

    def dragEnterEvent(self, event) -> None:
        if FileTable._has_local_urls(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if FileTable._has_local_urls(event):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.add_files(paths)
            event.acceptProposedAction()

    @property
    def files(self) -> list[Path]:
        return list(self._files)

    def add_files(self, paths: list[Path]) -> None:
        changed = False
        existing = {str(path).casefold() for path in self._files}
        for path in paths:
            path = Path(path)
            if path.suffix.lower() not in {".xlsx", ".xlsm"} or not path.is_file():
                continue
            key = str(path).casefold()
            if key not in existing:
                self._files.append(path)
                existing.add(key)
                changed = True
        if changed:
            self._refresh()
            self.files_changed.emit(self.files)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            del self._files[row]
        self._refresh()
        self.files_changed.emit(self.files)

    def clear(self) -> None:
        if not self._files:
            return
        self._files.clear()
        self._refresh()
        self.files_changed.emit(self.files)

    def _refresh(self) -> None:
        self.table.setRowCount(len(self._files))
        for row, path in enumerate(self._files):
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            self.table.setItem(row, 1, QTableWidgetItem(str(path.parent)))
        self._update_actions()

    def _update_actions(self) -> None:
        self.remove_button.setEnabled(bool(self.table.selectionModel() and self.table.selectionModel().hasSelection()))
        self.clear_button.setEnabled(bool(self._files))
