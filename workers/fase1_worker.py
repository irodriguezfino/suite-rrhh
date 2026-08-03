"""Ejecucion de Fase 1 fuera del hilo de interfaz."""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

from core.exceptions import ProcessingCancelled
from core.models import ProcessRequest
from services.fase1_service import Fase1Service


class Fase1Worker(QObject):
    progress = Signal(object)
    finished = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()

    def __init__(self, request: ProcessRequest) -> None:
        super().__init__()
        self._request = request
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        """Es seguro invocarlo desde el hilo de la interfaz."""
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            result = Fase1Service().run(
                self._request,
                progress_listener=self.progress.emit,
                should_cancel=self._cancel_event.is_set,
            )
        except ProcessingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())
        else:
            self.finished.emit(result)
