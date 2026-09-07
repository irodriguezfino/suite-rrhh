"""Proceso aislado del Comparador de Tempo.

Excel/COM y la lectura de libros se ejecutan fuera del proceso Qt. Así, un fallo
nativo de Excel no puede cerrar la ventana de Suite RRHH ni corromper su estado.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.exceptions import ProcessingCancelled
from core.models import ComparatorIncident, ComparatorRequest, ComparatorResult, ComparatorRow, ProgressUpdate
from services.comparador_tempo_service import ComparadorTempoService


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(path)


def _append_event(path: Path, event: str, **payload: Any) -> None:
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"timestamp": datetime.now().isoformat(timespec="seconds"), "event": event, **payload}, ensure_ascii=False, default=str) + "\n")
            handle.flush()
    except OSError:
        pass


def request_from_payload(payload: dict[str, Any]) -> ComparatorRequest:
    return ComparatorRequest(Path(payload["tempo_path"]), Path(payload["sap_path"]), Path(payload["output_path"]))


def _row_payload(row: ComparatorRow) -> dict[str, Any]:
    return {
        "section": row.section,
        "sap_code": row.sap_code,
        "worker": row.worker,
        "values_minutes": row.values_minutes,
        "trigger_fields": list(row.trigger_fields),
        "incidence_messages": list(row.incidence_messages),
        "sap_daily_work_minutes": row.sap_daily_work_minutes,
        "suppressed_fields": list(row.suppressed_fields),
        "sap_daily_minus_noise_minutes": row.sap_daily_minus_noise_minutes,
        "red_fields": list(row.red_fields),
    }


def _incident_payload(item: ComparatorIncident) -> dict[str, Any]:
    return {
        "incident_type": item.incident_type, "section": item.section, "sap_code": item.sap_code,
        "tempo_worker": item.tempo_worker, "sap_worker": item.sap_worker, "field": item.field,
        "tempo_minutes": item.tempo_minutes, "sap_minutes": item.sap_minutes,
        "difference_minutes": item.difference_minutes, "reason": item.reason,
        "tempo_values_minutes": item.tempo_values_minutes, "sap_values_minutes": item.sap_values_minutes,
    }


def result_to_payload(result: ComparatorResult) -> dict[str, Any]:
    return {
        "output_path": str(result.output_path), "incidents_path": str(result.incidents_path),
        "rows": [_row_payload(row) for row in result.rows],
        "incidents": [_incident_payload(item) for item in result.incidents],
        "sections": list(result.sections), "elapsed_seconds": result.elapsed_seconds,
        "detail_lines": list(result.detail_lines),
    }


def run(request_file: Path, result_file: Path, events_file: Path, cancel_file: Path) -> int:
    request = request_from_payload(json.loads(request_file.read_text(encoding="utf-8")))
    _append_event(events_file, "runner_started")

    def report(update: ProgressUpdate) -> None:
        _append_event(events_file, "progress", update={
            "event": update.event, "message": update.message, "completed_units": update.completed_units,
            "total_units": update.total_units, "rows": update.rows,
        })

    try:
        result = ComparadorTempoService().run(request, progress_listener=report, should_cancel=cancel_file.exists)
    except ProcessingCancelled:
        _write_json(result_file, {"state": "cancelled"})
        _append_event(events_file, "cancelled")
        return 0
    except Exception as exc:
        detail = traceback.format_exc()
        _write_json(result_file, {"state": "failed", "message": str(exc), "detail": detail})
        _append_event(events_file, "error", message=str(exc), detail=detail)
        return 1
    _write_json(result_file, {"state": "success", "result": result_to_payload(result)})
    _append_event(events_file, "success", output_path=str(result.output_path))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ejecutor aislado del Comparador de Tempo")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--events-file", required=True)
    parser.add_argument("--cancel-file", required=True)
    args = parser.parse_args()
    return run(Path(args.request_file), Path(args.result_file), Path(args.events_file), Path(args.cancel_file))


if __name__ == "__main__":
    raise SystemExit(main())
