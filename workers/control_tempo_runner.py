"""Proceso auxiliar aislado para ejecutar Control Tempo sin afectar a PySide6."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# Al ejecutarse como fichero con pythonw.exe, la raíz de la aplicación no forma
# parte de sys.path. Añadirla permite usar los mismos módulos que la interfaz.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exceptions import ProcessingCancelled
from core.models import ProcessRequest, ProcessResult, ProgressUpdate
from services.fase1_service import Fase1Service


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def _append_event(path: Path, event: str, **payload: Any) -> None:
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **payload,
    }
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            handle.flush()
    except OSError:
        # La ejecución no debe abortarse solo porque el canal de progreso falle.
        pass


def request_from_payload(payload: dict[str, Any]) -> ProcessRequest:
    return ProcessRequest(
        input_files=tuple(Path(value) for value in payload["input_files"]),
        selected_date=datetime.fromisoformat(payload["selected_date"]),
        output_path=Path(payload["output_path"]),
        employment_mode=str(payload["employment_mode"]),
        process_mode=str(payload["process_mode"]),
    )


def result_to_payload(result: ProcessResult) -> dict[str, Any]:
    return {
        "output_path": str(result.output_path),
        "worker_count": result.worker_count,
        "elapsed_seconds": result.elapsed_seconds,
        "detail_lines": list(result.detail_lines),
        "audits": list(result.audits),
    }


def run(request_file: Path, result_file: Path, events_file: Path, cancel_file: Path) -> int:
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    request = request_from_payload(payload)
    _append_event(events_file, "runner_started", process_mode=request.process_mode, files=len(request.input_files))

    def report(update: ProgressUpdate) -> None:
        _append_event(events_file, "progress", update={
            "event": update.event,
            "message": update.message,
            "completed_files": update.completed_files,
            "total_files": update.total_files,
            "completed_units": update.completed_units,
            "total_units": update.total_units,
            "rows": update.rows,
            "file_name": update.file_name,
            "technical": update.technical,
        })

    try:
        result = Fase1Service().run(
            request,
            progress_listener=report,
            should_cancel=cancel_file.exists,
        )
    except ProcessingCancelled:
        _write_json(result_file, {"state": "cancelled"})
        _append_event(events_file, "cancelled")
        return 0
    except Exception as exc:
        detail = traceback.format_exc()
        _write_json(result_file, {"state": "failed", "message": str(exc), "detail": detail})
        _append_event(events_file, "error", message=str(exc), detail=detail)
        return 1
    else:
        _write_json(result_file, {"state": "success", "result": result_to_payload(result)})
        _append_event(events_file, "success", output_path=str(result.output_path))
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecutor aislado de Control Tempo")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--events-file", required=True)
    parser.add_argument("--cancel-file", required=True)
    args = parser.parse_args()
    return run(Path(args.request_file), Path(args.result_file), Path(args.events_file), Path(args.cancel_file))


if __name__ == "__main__":
    raise SystemExit(main())
