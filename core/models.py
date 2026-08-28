"""Modelos tipados que conectan la interfaz PySide6 con los servicios."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProcessRequest:
    input_files: tuple[Path, ...]
    selected_date: datetime
    output_path: Path
    employment_mode: str
    process_mode: str


@dataclass(frozen=True)
class ProgressUpdate:
    event: str
    message: str
    completed_files: int = 0
    total_files: int = 0
    completed_units: int = 0
    total_units: int = 1
    rows: int = 0
    file_name: str = ""
    technical: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessResult:
    output_path: Path
    worker_count: int
    elapsed_seconds: float
    detail_lines: tuple[str, ...]
    audits: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ComparatorRequest:
    """Entradas del Comparador de Tempo.

    ``tempo_path`` se consulta sobre una copia temporal: así se respetan sus
    filtros de fecha y el archivo elegido por la persona usuaria no se altera.
    """

    tempo_path: Path
    sap_path: Path
    output_path: Path


@dataclass(frozen=True)
class ComparatorRow:
    section: str
    sap_code: str
    worker: str
    values_minutes: dict[str, int]
    trigger_fields: tuple[str, ...] = ()
    incidence_messages: tuple[str, ...] = ()
    sap_daily_work_minutes: int | None = None
    suppressed_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComparatorIncident:
    incident_type: str
    section: str
    sap_code: str
    tempo_worker: str
    sap_worker: str
    field: str
    tempo_minutes: int | None
    sap_minutes: int | None
    difference_minutes: int | None
    reason: str
    tempo_values_minutes: dict[str, int] = field(default_factory=dict)
    sap_values_minutes: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ComparatorResult:
    output_path: Path
    incidents_path: Path
    rows: tuple[ComparatorRow, ...]
    incidents: tuple[ComparatorIncident, ...]
    sections: tuple[str, ...]
    elapsed_seconds: float
    detail_lines: tuple[str, ...]
