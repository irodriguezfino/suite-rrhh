"""Bloqueo cooperativo de destino para evitar recopilaciones competidoras."""

from __future__ import annotations

import msvcrt
from pathlib import Path

from core.exceptions import OutputInUseError


class OutputLock:
    """Bloquea un destino Excel durante toda la recopilación en Windows.

    El bloqueo del sistema operativo se libera incluso si el proceso termina de
    forma inesperada. El fichero auxiliar solo identifica el recurso ocupado.
    """

    def __init__(self, output_path: Path) -> None:
        self.output_path = Path(output_path)
        self.lock_path = self.output_path.with_name(f".{self.output_path.name}.lock")
        self._handle = None

    def __enter__(self) -> "OutputLock":
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.lock_path.open("a+b")
        self._handle.seek(0, 2)
        if self._handle.tell() == 0:
            self._handle.write(b"0")
            self._handle.flush()
        self._handle.seek(0)
        try:
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise OutputInUseError(
                f"Ya hay una recopilación generando este archivo: {self.output_path.name}. "
                "Espera a que termine o elige otro destino."
            ) from exc
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._handle.close()
            self._handle = None
        try:
            self.lock_path.unlink()
        except OSError:
            pass
