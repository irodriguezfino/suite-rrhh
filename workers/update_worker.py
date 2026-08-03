"""Consulta remota de actualizaciones fuera del hilo de la interfaz."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from services.update_service import UpdateService


class UpdateWorker(QObject):
    available = Signal(object)
    unavailable = Signal()
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            update = UpdateService().check_for_update()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            if update is None:
                self.unavailable.emit()
            else:
                self.available.emit(update)
