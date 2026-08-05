"""Fachada de Fase 1 para interfaces de escritorio o ejecuciones futuras."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Callable

import openpyxl

from core.exceptions import BatchProcessingError
from core.models import ProcessRequest, ProcessResult, ProgressUpdate
from services.diagnostics import RunDiagnostics
from services.output_lock import OutputLock
from fase1_recopilacion import (
    EMPLOYMENT_MODE_ACTIVE,
    EMPLOYMENT_MODE_INACTIVE,
    PROCESS_MODE_DAILY,
    PROCESS_MODE_MONTHLY,
    CONTROL_SHEET,
    ExcelCollector,
    MONTHLY_CONTROL_SHEET,
    MONTH_SHEETS,
    get_next_month,
    get_previous_month,
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

    def preflight_sources(self, request: ProcessRequest) -> None:
        """Verifica que todos los partes pueden usarse antes de iniciar Excel en paralelo."""
        required_sheets = self._required_sheets(request)
        failures: list[tuple[str, str]] = []
        for path in request.input_files:
            source = Path(path)
            try:
                workbook = openpyxl.load_workbook(
                    source,
                    read_only=True,
                    data_only=False,
                    keep_vba=source.suffix.lower() == ".xlsm",
                )
                try:
                    available = {name.casefold() for name in workbook.sheetnames}
                finally:
                    workbook.close()
                missing = [sheet for sheet in required_sheets if sheet.casefold() not in available]
                if missing:
                    failures.append((source.name, f"faltan las hojas requeridas: {', '.join(missing)}"))
            except Exception as exc:
                failures.append((source.name, f"no se puede abrir o validar el libro: {exc}"))
        if failures:
            raise BatchProcessingError(failures)

    @staticmethod
    def _required_sheets(request: ProcessRequest) -> tuple[str, ...]:
        selected = request.selected_date.date()
        selected_sheet = MONTH_SHEETS[selected.month - 1]
        if request.process_mode == PROCESS_MODE_DAILY:
            return (selected_sheet, CONTROL_SHEET)
        previous_year, previous_month = get_previous_month(selected.year, selected.month)
        _next_year, next_month = get_next_month(selected.year, selected.month)
        required = [MONTH_SHEETS[previous_month - 1], selected_sheet, MONTHLY_CONTROL_SHEET]
        if selected.day >= 21:
            required.append(MONTH_SHEETS[next_month - 1])
        return tuple(dict.fromkeys(required))

    def run(
        self,
        request: ProcessRequest,
        progress_listener: ProgressListener | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> ProcessResult:
        self.validate(request)
        start = time.perf_counter()
        diagnostics = RunDiagnostics("control_tempo")
        diagnostics.record(
            "run_started",
            process_mode=request.process_mode,
            selected_date=request.selected_date.isoformat(),
            output_path=str(request.output_path),
            input_files=[str(path) for path in request.input_files],
        )
        completed_units = 0
        total_units = max(len(request.input_files) * 9 + 1, 1)

        def emit(payload: dict) -> None:
            nonlocal completed_units, total_units
            diagnostics.record("progress", payload=payload)
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

        try:
            self.preflight_sources(request)
            with OutputLock(request.output_path):
                collector = ExcelCollector(
                    request.selected_date,
                    request.output_path,
                    max_workers="auto",
                    employment_mode=request.employment_mode,
                    process_mode=request.process_mode,
                )
                collector.run(list(request.input_files), progress_callback=emit, should_cancel=should_cancel)
        except Exception as exc:
            diagnostics.record_exception(exc)
            raise

        detail_lines = [
            "RESUMEN FINAL",
            f"Archivo generado: {request.output_path}",
            f"Trabajadores exportados: {len(collector.rows)}",
            f"Tiempo total: {time.perf_counter() - start:.1f}s",
            f"Registro técnico: {diagnostics.path}",
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
