"""Bounded I/O tasks; consume the result only after QThread.finished."""
from PySide6.QtCore import QThread


class BackgroundTask(QThread):
    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.value = None
        self.error = None

    def run(self):
        try:
            self.value = self.operation()
        except Exception as exc:
            self.error = str(exc)
