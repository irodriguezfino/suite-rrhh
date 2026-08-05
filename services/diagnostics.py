"""Registro persistente y ligero de ejecuciones de Control Tempo."""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any


class RunDiagnostics:
    """Guarda eventos del proceso fuera de la carpeta de instalación."""

    def __init__(self, operation: str) -> None:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Suite RRHH" / "logs"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = root / f"{operation}_{timestamp}.jsonl"
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.path = Path.cwd() / f"{operation}_{timestamp}.jsonl"

    def record(self, event: str, **data: Any) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **data,
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # El diagnóstico nunca debe impedir una recopilación válida.
            pass

    def record_exception(self, exc: Exception) -> None:
        self.record("error", error=str(exc), traceback=traceback.format_exc())
