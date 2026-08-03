"""Excepciones funcionales compartidas por el motor y la aplicacion."""


class ProcessingCancelled(RuntimeError):
    """El usuario solicito detener la operacion en curso de forma segura."""


class OutputInUseError(RuntimeError):
    """Otro proceso ya está generando el mismo archivo de salida."""
