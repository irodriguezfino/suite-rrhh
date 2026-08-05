"""Excepciones funcionales compartidas por el motor y la aplicacion."""


class ProcessingCancelled(RuntimeError):
    """El usuario solicito detener la operacion en curso de forma segura."""


class OutputInUseError(RuntimeError):
    """Otro proceso ya está generando el mismo archivo de salida."""


class BatchProcessingError(RuntimeError):
    """Uno o varios partes no pudieron procesarse sin comprometer la salida."""

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = tuple(failures)
        summary = "\n".join(f"- {name}: {reason}" for name, reason in self.failures)
        super().__init__(
            f"No se ha generado el Excel final porque fallaron {len(self.failures)} parte(s):\n{summary}"
        )
