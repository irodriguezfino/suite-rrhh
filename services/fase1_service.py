"""Fachada de Fase 1 para interfaces de escritorio o ejecuciones futuras."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Callable

from core.models import ProcessRequest, ProcessResult, ProgressUpdate
from services.output_lock import OutputLock
from fase1_recopilacion import (
    EMPLOYMENT_MODE_ACTIVE,
    EMPLOYMENT_MODE_INACTIVE,
    PROCESS_MODE_DAILY,
    PROCESS_MODE_MONTHLY,
    ExcelCollector,
)

ProgressListener = Callable[[ProgressUpdate], None]
CancellationCheck = Callable[[], bool]


class Fase1Service:
    """Valida y ejecuta la recopilacion sin conocer la interfaz grafica."""

    def validate(self, request: ProcessRequest) -> None:
        if not request.input_files:
            raise ValueError("Selecciona al menos un archivo Excel de entrada.")
        missing = [path.name for path in request.input_files if not Path(path).is_file()]
        if missing:
            raise ValueError(f"No se encuentran los archivos de entrada: {', '.join(missing)}")
        if request.selected_date.date() > date.today():
            raise ValueError("La fecha de consulta no puede ser posterior a hoy.")
        if request.process_mode not in (PROCESS_MODE_DAILY, PROCESS_MODE_MONTHLY):
            raise ValueError("Selecciona proceso diario o mensual 20–20.")
        if request.employment_mode not in (EMPLOYMENT_MODE_ACTIVE, EMPLOYMENT_MODE_INACTIVE):
            raise ValueError("El tipo de trabajadores seleccionado no es válido.")
        if request.output_path.suffix.lower() != ".xlsx":
            raise ValueError("El archivo de salida debe tener extensión .xlsx.")

    def run(
        self,
        request: ProcessRequest,
        progress_listener: ProgressListener | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> ProcessResult:
        self.validate(request)
        start = time.perf_counter()
        completed_units = 0
        total_units = max(len(request.input_files) * 9 + 1, 1)

        def emit(payload: dict) -> None:
            nonlocal completed_units, total_units
            total_units = int(payload.get("total_units", total_units) or total_units)
            completed_units = min(total_units, completed_units + int(payload.get("progress_units", 0) or 0))
            if payload.get("event") == "file_completed":
                completed_files = int(payload.get("completed_files", 0) or 0)
            else:
                completed_files = int(payload.get("completed_files", 0) or 0)
            if progress_listener:
                progress_listener(ProgressUpdate(
                    event=str(payload.get("event", "")),
                    message=str(payload.get("message", "")),
                    completed_files=completed_files,
                    total_files=int(payload.get("total_files", len(request.input_files)) or len(request.input_files)),
                    completed_units=completed_units,
                    total_units=total_units,
                    rows=int(payload.get("rows", 0) or 0),
                    file_name=Path(str(payload.get("file", ""))).name,
                    technical=dict(payload),
                ))

        with OutputLock(request.output_path):
            collector = ExcelCollector(
                request.selected_date,
                request.output_path,
                max_workers="auto",
                employment_mode=request.employment_mode,
                process_mode=request.process_mode,
            )
            collector.run(list(request.input_files), progress_callback=emit, should_cancel=should_cancel)

        detail_lines = [
            "RESUMEN FINAL",
            f"Archivo generado: {request.output_path}",
            f"Trabajadores exportados: {len(collector.rows)}",
            f"Tiempo total: {time.perf_counter() - start:.1f}s",
            "Detalle por archivo:",
        ]
        for result in collector.results:
            detail_lines.append(
                f"{result.source_file}: {len(result.rows)} registros, auditoría="
                f"{result.audit.get('status', 'OK')}, {result.elapsed_seconds:.1f}s"
            )
        return ProcessResult(
            output_path=request.output_path,
            worker_count=len(collector.rows),
            elapsed_seconds=time.perf_counter() - start,
            detail_lines=tuple(detail_lines),
            audits=tuple(result.audit for result in collector.results),
        )
