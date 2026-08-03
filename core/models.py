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
