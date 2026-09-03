"""Motor verificable del Comparador de Tempo.

El libro de Tempo contiene una tabla dinámica con sus filtros temporales ya
configurados. Para no modificarlo, Excel abre una copia temporal y recorre las
secciones de la propia tabla dinámica conservando el resto de filtros (incluido
el de fecha). El informe SAP puede ser XML Spreadsheet 2003 o un libro moderno
XLSX/XLSM; se lee en modo solo lectura y nunca se altera el Excel de origen.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Callable, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.exceptions import ProcessingCancelled
from core.models import ComparatorIncident, ComparatorRequest, ComparatorResult, ComparatorRow, ProgressUpdate
from services.diagnostics import RunDiagnostics
from services.output_lock import OutputLock


TEMPO_SHEET = "PARALELO NUEVO"
TEMPO_DATA_SHEET = "DATOS"
TIME_COLUMNS = (
    "H. EXTRAS", "HFJ (15%)", "BOLSA (X%)", "NOCTUR", "PENOS", "RUIDO", "ABSENT",
)
COMPARISON_COLUMNS = TIME_COLUMNS[:-1]
RESULT_COLUMNS = (
    "Trabajador", "Incidencias", "Trab. Día SAP",
    *[f"Δ {field}" for field in COMPARISON_COLUMNS], "ABSENT",
)
SAP_FIELD_BY_TEMPO = {
    "H. EXTRAS": "1129-HE15%",
    "HFJ (15%)": "1166-HE30%",
    "BOLSA (X%)": "1166-HE35%",
    "NOCTUR": "1014-HNOC",
    "PENOS": "1146-PPEN",
    "RUIDO": "Trab. Dia",
}
SAP_COLUMNS = tuple(SAP_FIELD_BY_TEMPO.values())
# ABSENT es una incidencia de Tempo que siempre debe mostrarse. Las horas
# extras y HFJ se tratan como el resto de conceptos: solo se incluyen si su
# acumulado no coincide con el total correspondiente de SAP.
REQUIRED_DIRECT_VALUES = ("ABSENT",)
TOLERANCE_MINUTES = 1
MISSING_MARKING_MESSAGES = frozenset({"Falta fichaje de entrada", "Falta fichaje de salida"})
COMBINED_EXTRA_BOLSA_SECTIONS = frozenset({"ML", "MS", "MC", "MV"})
OUTPUT_REPLACE_ATTEMPTS = 12
OUTPUT_REPLACE_DELAY_SECONDS = 0.25
XML_NS = "{urn:schemas-microsoft-com:office:spreadsheet}"


def _normalise_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\xa0", " ").strip().split())
    return text


def _normalise_header(value: object) -> str:
    return _normalise_text(value).upper().replace(" ", "")


def _worker_key(value: object) -> str:
    text = _normalise_text(value).upper()
    return re.sub(r"[^A-Z0-9]", "", text)


def _sap_code(value: object) -> str:
    match = re.search(r"\b(\d{3,})\b", _normalise_text(value))
    return match.group(1) if match else ""


def _worker_identity(value: object) -> tuple[str, str] | None:
    """Devuelve solo etiquetas de trabajador, nunca una fecha de detalle."""
    text = _normalise_text(value)
    match = re.match(r"^\s*(\d{3,})\s+([^\d].*?)\s*$", text)
    if not match:
        return None
    return match.group(1), match.group(2).strip()


def _is_empty_mark(value: object) -> bool:
    return _normalise_text(value).strip() in {"", "-", "--"}


def _marking_incidence(first_mark: object, second_mark: object) -> str | None:
    """Clasifica un marcaje diario incompleto según las reglas de negocio."""
    if not _is_empty_mark(second_mark):
        return None
    first = _normalise_text(first_mark).strip()
    if first.casefold() == "festivo":
        return None
    if not first:
        return "Falta fichaje de entrada"
    # En el SAP el fichaje puede ser, por ejemplo, "[55] E 05:23".
    if re.search(r"\[\s*[^\]]+\]\s*(?:[ES]\s*)?\d{1,2}:\d{2}", first, flags=re.IGNORECASE):
        return "Falta fichaje de salida"
    return first


def _signed_minutes_text(minutes: int) -> str:
    """Formato legible y seguro para diferencias negativas en Excel."""
    sign = "+" if minutes > 0 else "-" if minutes < 0 else ""
    absolute = abs(minutes)
    return f"{sign}{absolute // 60}:{absolute % 60:02d}"


def _to_minutes(value: object) -> int:
    """Convierte una hora de Excel/SAP a minutos, redondeando segundos."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, timedelta):
        return int(round(value.total_seconds() / 60))
    if isinstance(value, datetime):
        return value.hour * 60 + value.minute + int(round(value.second / 60))
    if isinstance(value, clock_time):
        return value.hour * 60 + value.minute + int(round(value.second / 60))
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return 0
        # Excel entrega horas como fracción de día. Un número alto es muy poco
        # probable como duración y se conserva como minutos para no multiplicar
        # un dato anómalo por 1.440 silenciosamente.
        return int(round(float(value) * 1440 if abs(float(value)) <= 3 else float(value)))
    text = _normalise_text(value).replace("�", "")
    if not text or text in {"-", "--", "N/A"}:
        return 0
    text = text.replace(",", ".")
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    if ":" in text:
        parts = text.split(":")
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            seconds = int(parts[2]) if len(parts) > 2 else 0
            return sign * (hours * 60 + minutes + int(round(seconds / 60)))
        except ValueError:
            return 0
    try:
        number = float(text)
    except ValueError:
        return 0
    return sign * int(round(number * 1440 if abs(number) <= 3 else number))


def _minutes_as_excel(minutes: int | None) -> float | None:
    return None if minutes is None else minutes / 1440


def _time_text(minutes: int | None) -> str:
    if minutes is None:
        return ""
    sign = "-" if minutes < 0 else ""
    absolute = abs(minutes)
    return f"{sign}{absolute // 60}:{absolute % 60:02d}"


def _matrix(value: object) -> list[list[object]]:
    if value is None:
        return []
    if not isinstance(value, tuple):
        return [[value]]
    if not value:
        return []
    if isinstance(value[0], tuple):
        return [list(row) for row in value]
    return [list(value)]


class ComparadorTempoService:
    """Compara el resultado filtrado de Tempo con los totales SAP."""

    def __init__(
        self,
        tempo_reader: Callable[[Path, Callable[[], bool], Callable[[str, int, int], None]], dict[str, list[dict]]] | None = None,
        identity_loader: Callable[[Path], tuple[dict[str, dict[str, set[str]]], list[ComparatorIncident]]] | None = None,
        sap_reader: Callable[[Path], tuple[dict[str, dict], set[str]]] | None = None,
    ) -> None:
        # La inyección permite probar toda la comparación sin Excel/COM.
        self._tempo_reader = tempo_reader or self._read_tempo_by_section
        self._identity_loader = identity_loader or self._load_tempo_identities
        self._sap_reader = sap_reader or self._read_sap_totals

    def run(
        self,
        request: ComparatorRequest,
        progress_listener: Callable[[ProgressUpdate], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ComparatorResult:
        started = time.perf_counter()
        diagnostics = RunDiagnostics("comparador_tempo")
        cancelled = should_cancel or (lambda: False)

        def check_cancel() -> None:
            if cancelled():
                raise ProcessingCancelled("Comparación cancelada por el usuario.")

        def report(message: str, current: int = 0, total: int = 1, *, rows: int = 0, event: str = "progress") -> None:
            if progress_listener:
                progress_listener(ProgressUpdate(event=event, message=message, completed_units=current, total_units=max(total, 1), rows=rows))
            diagnostics.record("progress", message=message, current=current, total=total, rows=rows)

        request = ComparatorRequest(Path(request.tempo_path), Path(request.sap_path), Path(request.output_path))
        self._validate_request(request)
        report("Leyendo la relación de trabajadores de Tempo…", 0, 8)
        identity_map, identity_issues = self._identity_loader(request.tempo_path)
        check_cancel()

        def tempo_progress(label: str, current: int, total: int) -> None:
            report(f"Leyendo sección {label} de Tempo…", 1 + current, max(total + 4, 8))

        report("Abriendo la tabla dinámica de Tempo sin modificar el original…", 1, 8)
        tempo_sections = self._tempo_reader(request.tempo_path, cancelled, tempo_progress)
        check_cancel()
        report("Leyendo totales del informe SAP…", 4, 8)
        sap_workers, sap_duplicates = self._sap_reader(request.sap_path)
        check_cancel()
        report("Comparando códigos y acumulados…", 5, 8)
        rows, incidents = self._compare(tempo_sections, identity_map, identity_issues, sap_workers, sap_duplicates, check_cancel)
        check_cancel()
        report("Generando Excel de resultado e incidencias…", 6, 8, rows=len(rows), event="writing")
        requested_incidents_path = request.output_path.with_name(f"{request.output_path.stem}_incidencias.xlsx")
        output_path, incidents_path = self._write_outputs(request.output_path, requested_incidents_path, rows, incidents)
        elapsed = time.perf_counter() - started
        detail = (
            f"Secciones analizadas: {len(tempo_sections)}",
            f"Trabajadores incluidos en resultado: {len(rows)}",
            f"Incidencias de auditoría: {len(incidents)}",
            f"Tolerancia de comparación: {TOLERANCE_MINUTES} minuto.",
            "Se conservaron los filtros ya configurados en la tabla dinámica de Tempo.",
        )
        if output_path != request.output_path or incidents_path != requested_incidents_path:
            detail += ("Algún archivo de salida estaba bloqueado; se guardó una copia recuperada con un nombre alternativo.",)
        diagnostics.record("success", output=str(output_path), incidents=str(incidents_path), rows=len(rows), incidents_count=len(incidents))
        report("Comparación terminada correctamente.", 8, 8, rows=len(rows), event="completed")
        return ComparatorResult(
            output_path,
            incidents_path,
            tuple(rows),
            tuple(incidents),
            tuple(sorted({row.section for row in rows})),
            elapsed,
            detail,
        )

    @staticmethod
    def _validate_request(request: ComparatorRequest) -> None:
        for label, path in (("El Excel de Tempo", request.tempo_path), ("El informe SAP", request.sap_path)):
            if not path.is_file():
                raise FileNotFoundError(f"{label} no existe o no está disponible: {path}")
        if request.tempo_path.resolve() == request.output_path.resolve() or request.sap_path.resolve() == request.output_path.resolve():
            raise ValueError("El Excel de salida no puede sustituir ninguno de los archivos de entrada.")
        if request.output_path.suffix.lower() != ".xlsx":
            raise ValueError("El resultado debe guardarse como archivo .xlsx.")
        if request.sap_path.suffix.lower() not in {".xls", ".xml", ".xlsx", ".xlsm"}:
            raise ValueError(
                "El informe SAP debe ser un Excel XML (.xls o .xml) o un libro moderno (.xlsx o .xlsm)."
            )

    def _load_tempo_identities(self, path: Path) -> tuple[dict[str, dict[str, set[str]]], list[ComparatorIncident]]:
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except PermissionError as exc:
            raise RuntimeError(
                "No se puede leer el Excel de Tempo porque está abierto o bloqueado. "
                "Ciérralo en Excel o selecciona una copia antes de comparar."
            ) from exc
        try:
            if TEMPO_DATA_SHEET not in workbook.sheetnames:
                raise ValueError(f"No se encontró la hoja {TEMPO_DATA_SHEET!r} en el Excel de Tempo.")
            sheet = workbook[TEMPO_DATA_SHEET]
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, None)
            if not headers:
                raise ValueError("La hoja DATOS de Tempo no tiene cabeceras.")
            positions = {_normalise_header(value): index for index, value in enumerate(headers)}
            for header in ("SECCION", "SAP", "TRABAJADOR"):
                if header not in positions:
                    raise ValueError(f"La hoja DATOS de Tempo no contiene la columna {header!r}.")
            identities: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
            for row in rows:
                section = _normalise_text(row[positions["SECCION"]] if positions["SECCION"] < len(row) else "")
                worker = _worker_key(row[positions["TRABAJADOR"]] if positions["TRABAJADOR"] < len(row) else "")
                code = _sap_code(row[positions["SAP"]] if positions["SAP"] < len(row) else "")
                if section and worker and code:
                    identities[section][worker].add(code)
            return {section: dict(workers) for section, workers in identities.items()}, []
        finally:
            workbook.close()

    def _read_tempo_by_section(self, path: Path, should_cancel: Callable[[], bool], progress: Callable[[str, int, int], None]) -> dict[str, list[dict]]:
        """Lee la tabla dinámica usando Excel COM sobre una copia temporal."""
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("No se encontró la automatización de Excel requerida para leer Tempo.") from exc

        with tempfile.TemporaryDirectory(prefix="suite_rrhh_tempo_") as directory:
            copied_path = Path(directory) / path.name
            shutil.copy2(path, copied_path)
            excel = None
            workbook = None
            try:
                excel = win32com.client.DispatchEx("Excel.Application")
                excel.Visible = False
                excel.DisplayAlerts = False
                excel.EnableEvents = False
                excel.AskToUpdateLinks = False
                try:
                    excel.AutomationSecurity = 3
                except Exception:
                    pass
                workbook = excel.Workbooks.Open(str(copied_path), UpdateLinks=0, ReadOnly=False)
                try:
                    sheet = workbook.Worksheets(TEMPO_SHEET)
                except Exception as exc:
                    raise ValueError(f"No se encontró la hoja {TEMPO_SHEET!r} en el Excel de Tempo.") from exc
                if sheet.PivotTables().Count < 1:
                    raise ValueError("La hoja PARALELO NUEVO no contiene una tabla dinámica utilizable.")
                pivot = sheet.PivotTables(1)
                field = pivot.PivotFields("SECCION")
                slicer_cache = self._find_section_slicer_cache(workbook, pivot)
                section_names = self._slicer_sections(slicer_cache) if slicer_cache is not None else self._pivot_sections(field)
                if not section_names:
                    raise ValueError("No se han encontrado secciones en la tabla dinámica de Tempo.")
                if slicer_cache is not None:
                    # Los trabajadores del libro están asociados de forma
                    # única a sección y código SAP en DATOS. Mostrar todo el
                    # slicer permite leer el pivote una única vez y conservar
                    # el filtro temporal activo, en vez de reconstruirlo por
                    # cada una de las secciones.
                    progress("todas las secciones", 1, 1)
                    self._select_all_slicer_sections(slicer_cache)
                    return {"": self._rows_from_pivot(_matrix(pivot.TableRange1.Value2))}
                result: dict[str, list[dict]] = {}
                for current, section in enumerate(section_names, start=1):
                    if should_cancel():
                        raise ProcessingCancelled("Comparación cancelada por el usuario.")
                    progress(section, current, len(section_names))
                    self._select_pivot_section(field, section, section_names, slicer_cache)
                    # La segmentación actualiza el resultado del pivote al
                    # cambiar de selección. Refrescar su caché aquí volvería a
                    # leer todo el origen por cada sección y multiplicaría el
                    # tiempo de proceso sin cambiar los datos filtrados.
                    rows = self._rows_from_pivot(_matrix(pivot.TableRange1.Value2))
                    result[section] = rows
                return result
            finally:
                if workbook is not None:
                    try:
                        workbook.Close(SaveChanges=False)
                    except Exception:
                        pass
                if excel is not None:
                    try:
                        excel.Quit()
                    except Exception:
                        pass

    @staticmethod
    def _pivot_sections(field) -> list[str]:
        result = []
        for index in range(1, field.PivotItems().Count + 1):
            name = _normalise_text(field.PivotItems(index).Name)
            if name and name.lower() not in {"(blank)", "(en blanco)"}:
                result.append(name)
        return sorted(set(result))

    @staticmethod
    def _slicer_sections(slicer_cache) -> list[str]:
        result = []
        items = slicer_cache.SlicerItems
        for index in range(1, items.Count + 1):
            name = _normalise_text(items.Item(index).Name)
            if name and name.lower() not in {"(blank)", "(en blanco)"}:
                result.append(name)
        return sorted(set(result))

    @staticmethod
    def _find_section_slicer_cache(workbook, pivot):
        """Localiza la segmentación SECCION asociada al pivote concreto.

        El libro tiene varias segmentaciones con el mismo campo, una por cada
        hoja. Comparar también la hoja evita filtrar un pivote diferente.
        """
        target_name = _normalise_text(pivot.Name)
        target_sheet = _normalise_text(pivot.Parent.Name)
        for index in range(1, workbook.SlicerCaches.Count + 1):
            try:
                cache = workbook.SlicerCaches(index)
                if _normalise_header(cache.SourceName) != "SECCION":
                    continue
                pivots = cache.PivotTables
                for pivot_index in range(1, pivots.Count + 1):
                    candidate = pivots.Item(pivot_index)
                    if (_normalise_text(candidate.Name) == target_name and
                            _normalise_text(candidate.Parent.Name) == target_sheet):
                        return cache
            except Exception:
                # Los TimelineCache no exponen SlicerItems/PivotTables como un
                # slicer convencional; se ignoran sin tocar sus filtros.
                continue
        return None

    @staticmethod
    def _select_pivot_section(field, target: str, sections: Iterable[str], slicer_cache=None) -> None:
        """Filtra un campo de filas sin tocar los filtros temporales del pivote."""
        if slicer_cache is not None:
            ComparadorTempoService._select_slicer_section(slicer_cache, target)
            return
        try:
            field.ClearAllFilters()
            field.CurrentPage = target
            return
        except Exception:
            pass
        # SECCION suele ser un campo de filas controlado por segmentación. Excel
        # no permite ocultar el último elemento visible; se asegura primero el
        # destino y después se ocultan los demás.
        try:
            field.PivotItems(target).Visible = True
        except Exception as exc:
            raise RuntimeError(f"No se pudo seleccionar la sección {target!r} en la tabla dinámica.") from exc
        for name in sections:
            if name == target:
                continue
            try:
                field.PivotItems(name).Visible = False
            except Exception:
                # Algunos pivotes retienen elementos ya no disponibles; no deben
                # impedir procesar los elementos que sí forman parte del filtro.
                continue

    @staticmethod
    def _select_slicer_section(slicer_cache, target: str) -> None:
        """Selecciona una única sección mediante su segmentación de datos."""
        items = slicer_cache.SlicerItems
        names = {_normalise_text(items.Item(index).Name) for index in range(1, items.Count + 1)}
        if target not in names:
            raise RuntimeError(f"La segmentación de secciones no contiene {target!r}.")
        try:
            # ClearManualFilter afecta únicamente a esta segmentación, no a la
            # línea temporal de fechas ni a los demás filtros de Tempo.
            slicer_cache.ClearManualFilter()
            for index in range(1, items.Count + 1):
                item = items.Item(index)
                if _normalise_text(item.Name) != target:
                    item.Selected = False
        except Exception as exc:
            raise RuntimeError(f"No se pudo seleccionar la sección {target!r} mediante su segmentación de datos.") from exc

    @staticmethod
    def _select_all_slicer_sections(slicer_cache) -> None:
        try:
            # Solo elimina la selección manual de SECCION. Las fechas se
            # controlan por TimelineCache independiente y permanecen intactas.
            slicer_cache.ClearManualFilter()
        except Exception as exc:
            raise RuntimeError("No se pudieron mostrar todas las secciones de la segmentación de Tempo.") from exc

    @staticmethod
    def _rows_from_pivot(matrix: list[list[object]]) -> list[dict]:
        if not matrix:
            return []
        header_index = next((index for index, row in enumerate(matrix) if _normalise_header(row[0] if row else "") == "ETIQUETASDEFILA"), None)
        if header_index is None:
            raise ValueError("No se reconocieron las cabeceras de la tabla dinámica PARALELO NUEVO.")
        rows: list[dict] = []
        for source in matrix[header_index + 1:]:
            if not source:
                continue
            worker = _normalise_text(source[0] if len(source) else "")
            if not worker or _normalise_header(worker).startswith("TOTALGENERAL"):
                continue
            values = {column: _to_minutes(source[index] if index < len(source) else 0) for index, column in enumerate(TIME_COLUMNS, start=1)}
            rows.append({"worker": worker, "values": values})
        return rows

    @staticmethod
    def _read_sap_totals(path: Path) -> tuple[dict[str, dict], set[str]]:
        if path.suffix.lower() in {".xlsx", ".xlsm"}:
            return ComparadorTempoService._read_sap_totals_xlsx(path)
        return ComparadorTempoService._read_sap_totals_xml(path)

    @staticmethod
    def _read_sap_totals_xml(path: Path) -> tuple[dict[str, dict], set[str]]:
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            raise ValueError(
                "El informe SAP debe ser un Excel XML 2003 (.xls o .xml) legible, "
                "o un libro moderno .xlsx."
            ) from exc
        rows = root.findall(f".//{XML_NS}Worksheet/{XML_NS}Table/{XML_NS}Row")
        return ComparadorTempoService._read_sap_totals_from_rows(
            ComparadorTempoService._xml_row_values(row) for row in rows
        )

    @staticmethod
    def _read_sap_totals_xlsx(path: Path) -> tuple[dict[str, dict], set[str]]:
        """Lee una exportación SAP XLSX sin cargar el libro completo en memoria."""
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except PermissionError as exc:
            raise RuntimeError(
                "No se puede leer el Excel Tempo SAP porque está abierto o bloqueado. "
                "Ciérralo en Excel o selecciona una copia antes de comparar."
            ) from exc
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ValueError("El informe SAP .xlsx no es legible o está dañado.") from exc

        missing_columns_error: ValueError | None = None
        try:
            for sheet in workbook.worksheets:
                try:
                    return ComparadorTempoService._read_sap_totals_from_rows(
                        ComparadorTempoService._xlsx_row_values(row)
                        for row in sheet.iter_rows(values_only=True)
                    )
                except ValueError as exc:
                    if "No se localizaron las columnas SAP necesarias" not in str(exc):
                        raise
                    missing_columns_error = exc
        finally:
            workbook.close()

        if missing_columns_error is not None:
            raise missing_columns_error
        raise ValueError("El informe SAP .xlsx no contiene hojas legibles.")

    @staticmethod
    def _read_sap_totals_from_rows(
        rows: Iterable[dict[int, object]],
    ) -> tuple[dict[str, dict], set[str]]:
        headers: dict[str, int] | None = None
        mark_columns: tuple[int, int] | None = None
        totals: dict[str, dict] = {}
        duplicate_codes: set[str] = set()
        pending: tuple[str, str] | None = None
        current_worker: tuple[str, str] | None = None
        marking_incidents: dict[str, list[str]] = defaultdict(list)
        for values in rows:
            if not values:
                continue
            if headers is None:
                by_header = {_normalise_header(value): column for column, value in values.items()}
                required = {_normalise_header(value) for value in SAP_COLUMNS}
                if required.issubset(by_header):
                    headers = {value: by_header[_normalise_header(value)] for value in SAP_COLUMNS}
                    marks = [column for column, value in values.items() if _normalise_header(value) == "MARCAJES"]
                    if len(marks) < 2:
                        raise ValueError("No se localizaron las dos columnas de marcajes del informe SAP.")
                    mark_columns = (marks[0], marks[1])
                continue
            label = _normalise_text(values.get(2, ""))
            if _normalise_header(label).startswith("GRANTOTAL"):
                break
            if pending is not None and any(column in values for column in headers.values()):
                code, worker = pending
                record = {
                    "worker": worker,
                    "values": {field: _to_minutes(values.get(column)) for field, column in headers.items()},
                    "marking_incidents": tuple(marking_incidents.get(code, ())),
                }
                if code in totals:
                    duplicate_codes.add(code)
                else:
                    totals[code] = record
                pending = None
                current_worker = None
                continue
            identity = _worker_identity(label)
            if identity is not None:
                if current_worker is not None and current_worker[0] == identity[0]:
                    # SAP repite la etiqueta de trabajador justo antes de su línea de total.
                    pending = identity
                else:
                    current_worker = identity
                continue
            if current_worker is None or mark_columns is None:
                continue
            # Las filas diarias tienen fecha en la columna de fecha. Se evalúan
            # también aunque los dos marcajes estén vacíos: eso es una entrada faltante.
            if label:
                message = _marking_incidence(values.get(mark_columns[0]), values.get(mark_columns[1]))
                if message and message not in marking_incidents[current_worker[0]]:
                    marking_incidents[current_worker[0]].append(message)
        if headers is None:
            expected = ", ".join(SAP_COLUMNS)
            raise ValueError(f"No se localizaron las columnas SAP necesarias: {expected}.")
        if not totals:
            raise ValueError("No se localizaron los totales por trabajador en el informe SAP.")
        return totals, duplicate_codes

    @staticmethod
    def _xml_row_values(row) -> dict[int, str]:
        values: dict[int, str] = {}
        column = 1
        for cell in row.findall(f"{XML_NS}Cell"):
            index = cell.attrib.get(f"{XML_NS}Index")
            if index:
                column = int(index)
            data = cell.find(f"{XML_NS}Data")
            values[column] = "" if data is None or data.text is None else data.text
            column += 1
        return values

    @staticmethod
    def _xlsx_row_values(row: tuple[object, ...]) -> dict[int, object]:
        """Conserva los índices de columna de una fila XLSX, incluidos huecos."""
        return {
            column: value
            for column, value in enumerate(row, start=1)
            if value is not None
        }

    def _compare(
        self,
        tempo_sections: dict[str, list[dict]],
        identities: dict[str, dict[str, set[str]]],
        identity_issues: list[ComparatorIncident],
        sap_workers: dict[str, dict],
        sap_duplicates: set[str],
        check_cancel: Callable[[], None],
    ) -> tuple[list[ComparatorRow], list[ComparatorIncident]]:
        result: list[ComparatorRow] = []
        incidents = list(identity_issues)
        matched_codes: set[str] = set()
        seen_tempo_codes: set[str] = set()
        global_identities: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for known_section, workers in identities.items():
            for worker_key, codes in workers.items():
                global_identities[worker_key].update((known_section, code) for code in codes)
        for source_section in sorted(tempo_sections):
            for tempo in tempo_sections[source_section]:
                check_cancel()
                worker = tempo["worker"]
                values = dict(tempo["values"])
                section = source_section
                codes = identities.get(section, {}).get(_worker_key(worker), set())
                if not section:
                    candidates = global_identities.get(_worker_key(worker), set())
                    if len(candidates) == 1:
                        section, code = next(iter(candidates))
                        codes = {code}
                if len(codes) != 1:
                    reason = "No se encontró un código SAP único para el trabajador en DATOS de Tempo."
                    if source_section:
                        if len(codes) > 1:
                            reason = "El trabajador tiene varios códigos SAP posibles en DATOS de Tempo."
                    else:
                        reason = "El trabajador no tiene una combinación única de sección y código SAP en DATOS de Tempo."
                    incidents.append(self._incident("Identidad no verificable", section, "", worker, "", "Código SAP", None, None, None, reason, values, {}))
                    continue
                code = next(iter(codes))
                seen_tempo_codes.add(code)
                sap = sap_workers.get(code)
                if sap is None:
                    incidents.append(self._incident("Solo en Tempo", section, code, worker, "", "Código SAP", None, None, None, "El código SAP de Tempo no existe en el informe SAP.", values, {}))
                    continue
                matched_codes.add(code)
                sap_values = dict(sap["values"])
                marking_messages = tuple(str(message) for message in sap.get("marking_incidents", ()))
                has_combined_extra_bolsa = _normalise_text(section).upper() in COMBINED_EXTRA_BOLSA_SECTIONS
                mismatches: list[tuple[str, int, int, int]] = []
                trigger_fields: set[str] = set()
                for tempo_field, sap_field in SAP_FIELD_BY_TEMPO.items():
                    if has_combined_extra_bolsa and tempo_field == "H. EXTRAS":
                        # En ML/MS/MC/MV las extras se liquidan conjuntamente
                        # en Bolsa; no tienen comparación independiente.
                        continue
                    compared_tempo_minutes = values[tempo_field]
                    comparison_name = tempo_field
                    reason_prefix = ""
                    if has_combined_extra_bolsa and tempo_field == "BOLSA (X%)":
                        compared_tempo_minutes = values["H. EXTRAS"] + values["BOLSA (X%)"]
                        comparison_name = "BOLSA (X%) · H. EXTRAS + BOLSA (X%)"
                        reason_prefix = "En esta sección se compara SAP 1166-HE35% con Tempo H. EXTRAS + BOLSA (X%). "
                    # La salida y la auditoría expresan siempre SAP menos Tempo.
                    difference = sap_values[sap_field] - compared_tempo_minutes
                    if abs(difference) > TOLERANCE_MINUTES:
                        mismatches.append((tempo_field, compared_tempo_minutes, sap_values[sap_field], difference))
                        trigger_fields.add(tempo_field)
                        incidents.append(self._incident("Diferencia", section, code, worker, sap["worker"], comparison_name, compared_tempo_minutes, sap_values[sap_field], difference, f"{reason_prefix}La diferencia supera {TOLERANCE_MINUTES} minuto.", values, sap_values))
                for message in marking_messages:
                    incidents.append(self._incident("Incidencia de marcaje", section, code, worker, sap["worker"], "Marcajes", None, None, None, message, values, sap_values))
                # La primera premisa no es una comparación: cualquier
                # absentismo real (también un único minuto) debe aparecer.
                direct = any(values[field] != 0 for field in REQUIRED_DIRECT_VALUES)
                if direct:
                    trigger_fields.update(field for field in REQUIRED_DIRECT_VALUES if values[field] != 0)
                # Las incidencias nominales (vacaciones, enfermedad, etc.) se
                # mantienen en el Excel de incidencias, pero no se imprimen en
                # el resultado si no hay nada que revisar. Un fichaje faltante
                # siempre requiere revisión y sí conserva su fila.
                missing_marking = any(message in MISSING_MARKING_MESSAGES for message in marking_messages)
                if direct or mismatches or missing_marking:
                    ordered_triggers = tuple(field for field in TIME_COLUMNS if field in trigger_fields)
                    displayed_values = {
                        field: (
                            values[field] if field == "ABSENT" else
                            0 if has_combined_extra_bolsa and field == "H. EXTRAS" else
                            sap_values[SAP_FIELD_BY_TEMPO[field]] - (values["H. EXTRAS"] + values["BOLSA (X%)"])
                            if has_combined_extra_bolsa and field == "BOLSA (X%)" else
                            sap_values[SAP_FIELD_BY_TEMPO[field]] - values[field]
                        )
                        for field in TIME_COLUMNS
                    }
                    result.append(ComparatorRow(
                        section, code, worker, displayed_values, ordered_triggers,
                        marking_messages, sap_values.get("Trab. Dia"),
                        ("H. EXTRAS",) if has_combined_extra_bolsa else (),
                    ))
                if code in sap_duplicates:
                    incidents.append(self._incident("Código SAP duplicado", section, code, worker, sap["worker"], "Código SAP", None, None, None, "El informe SAP contiene más de un total para este código; se ha usado el primero.", values, sap_values))
        for code, sap in sorted(sap_workers.items()):
            if code not in seen_tempo_codes:
                incidents.append(self._incident("Solo en SAP", "", code, "", sap["worker"], "Código SAP", None, None, None, "El código SAP no aparece en la tabla dinámica Tempo con sus filtros actuales.", {}, sap["values"]))
            if code in sap_duplicates and code not in matched_codes:
                incidents.append(self._incident("Código SAP duplicado", "", code, "", sap["worker"], "Código SAP", None, None, None, "El informe SAP contiene más de un total para este código; se ha usado el primero.", {}, sap["values"]))
        result.sort(key=lambda item: (item.section, _worker_key(item.worker), item.sap_code))
        return result, incidents

    @staticmethod
    def _incident(
        incident_type: str, section: str, code: str, tempo_worker: str, sap_worker: str,
        field: str, tempo_minutes: int | None, sap_minutes: int | None, difference: int | None,
        reason: str, tempo_values: dict[str, int], sap_values: dict[str, int],
    ) -> ComparatorIncident:
        return ComparatorIncident(incident_type, section, code, tempo_worker, sap_worker, field, tempo_minutes, sap_minutes, difference, reason, dict(tempo_values), dict(sap_values))

    def _write_outputs(self, output_path: Path, incidents_path: Path, rows: list[ComparatorRow], incidents: list[ComparatorIncident]) -> tuple[Path, Path]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with OutputLock(output_path), OutputLock(incidents_path):
            saved_output_path = self._save_main_workbook(output_path, rows)
            if saved_output_path != output_path:
                incidents_path = saved_output_path.with_name(f"{saved_output_path.stem}_incidencias.xlsx")
            saved_incidents_path = self._save_incidents_workbook(incidents_path, incidents)
        return saved_output_path, saved_incidents_path

    def _save_main_workbook(self, path: Path, rows: list[ComparatorRow]) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Resultado"
        sheet.sheet_view.showGridLines = False
        last_column = get_column_letter(len(RESULT_COLUMNS))
        sheet.merge_cells(f"A1:{last_column}1")
        sheet["A1"] = "Comparador de Tempo · Resultado"
        sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
        sheet["A1"].fill = PatternFill("solid", fgColor="123283")
        sheet["A1"].alignment = Alignment(horizontal="left")
        sheet.merge_cells(f"A2:{last_column}2")
        sheet["A2"] = "Δ = SAP − Tempo. Se incluyen diferencias superiores a un minuto, ABSENT de Tempo e incidencias de marcaje SAP."
        sheet["A2"].font = Font(italic=True, color="52627A")
        row_index = 4
        for section in sorted({row.section for row in rows}):
            sheet.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=len(RESULT_COLUMNS))
            cell = sheet.cell(row_index, 1, f"SECCIÓN · {section}")
            cell.fill = PatternFill("solid", fgColor="DCE8FF")
            cell.font = Font(bold=True, color="123283")
            row_index += 1
            for column_index, title in enumerate(RESULT_COLUMNS, start=1):
                cell = sheet.cell(row_index, column_index, title)
                cell.fill = PatternFill("solid", fgColor="123283")
                cell.font = Font(bold=True, color="FFFFFF")
                cell.alignment = Alignment(horizontal="center")
            row_index += 1
            for item in (row for row in rows if row.section == section):
                sheet.cell(row_index, 1, item.worker)
                incidence_cell = sheet.cell(row_index, 2, "; ".join(item.incidence_messages) if item.incidence_messages else "-")
                incidence_cell.alignment = Alignment(vertical="center", wrap_text=True)
                if item.incidence_messages:
                    incidence_cell.fill = PatternFill("solid", fgColor="FFF4CC")
                    incidence_cell.font = Font(bold=True, color="7A4C00")
                daily_cell = sheet.cell(row_index, 3, _minutes_as_excel(item.sap_daily_work_minutes))
                daily_cell.number_format = "[h]:mm"
                daily_cell.alignment = Alignment(horizontal="center")
                for column_index, title in enumerate(COMPARISON_COLUMNS, start=4):
                    cell = sheet.cell(
                        row_index,
                        column_index,
                        "-" if title in item.suppressed_fields else _signed_minutes_text(item.values_minutes[title]),
                    )
                    cell.alignment = Alignment(horizontal="center")
                    if title in item.trigger_fields:
                        cell.fill = PatternFill("solid", fgColor="FFF4CC")
                        cell.font = Font(bold=True, color="7A4C00")
                absent_cell = sheet.cell(row_index, len(RESULT_COLUMNS), _minutes_as_excel(item.values_minutes["ABSENT"]))
                absent_cell.number_format = "[h]:mm"
                absent_cell.alignment = Alignment(horizontal="center")
                if "ABSENT" in item.trigger_fields:
                    absent_cell.fill = PatternFill("solid", fgColor="FFF4CC")
                    absent_cell.font = Font(bold=True, color="7A4C00")
                row_index += 1
            row_index += 1
        if not rows:
            sheet.merge_cells(f"A4:{last_column}4")
            sheet["A4"] = "No se han encontrado trabajadores que cumplan las condiciones de comparación."
            sheet["A4"].font = Font(italic=True, color="52627A")
        widths = (34, 34, 15, 15, 15, 15, 14, 14, 14, 14)
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.freeze_panes = "A4"
        return self._atomic_save(workbook, path)

    def _save_incidents_workbook(self, path: Path, incidents: list[ComparatorIncident]) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Incidencias"
        sheet.sheet_view.showGridLines = False
        headers = (
            "Tipo", "Sección", "Código SAP", "Trabajador Tempo", "Trabajador SAP",
            *[f"Tempo · {field}" for field in TIME_COLUMNS],
            *[f"SAP · {field}" for field in SAP_COLUMNS],
            "Campo", "Valor Tempo", "Valor SAP", "Diferencia (min)", "Motivo",
        )
        for column, title in enumerate(headers, start=1):
            cell = sheet.cell(1, column, title)
            cell.fill = PatternFill("solid", fgColor="123283")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
        for row_index, item in enumerate(incidents, start=2):
            values: list[object] = [item.incident_type, item.section, item.sap_code, item.tempo_worker, item.sap_worker]
            values.extend(_minutes_as_excel(item.tempo_values_minutes.get(field)) if field in item.tempo_values_minutes else None for field in TIME_COLUMNS)
            values.extend(_minutes_as_excel(item.sap_values_minutes.get(field)) if field in item.sap_values_minutes else None for field in SAP_COLUMNS)
            values.extend([item.field, _minutes_as_excel(item.tempo_minutes), _minutes_as_excel(item.sap_minutes), item.difference_minutes, item.reason])
            for column, value in enumerate(values, start=1):
                cell = sheet.cell(row_index, column, value)
                cell.alignment = Alignment(vertical="top", wrap_text=column == len(headers))
                if 6 <= column < 6 + len(TIME_COLUMNS) + len(SAP_COLUMNS) or column in {len(headers) - 3, len(headers) - 2}:
                    cell.number_format = "[h]:mm"
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(sheet.max_row, 1)}"
        for index, title in enumerate(headers, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = 18 if "Trabajador" not in title and title != "Motivo" else (30 if "Trabajador" in title else 48)
        return self._atomic_save(workbook, path)

    @staticmethod
    def _atomic_save(workbook: Workbook, path: Path) -> Path:
        """Guarda sin corromper el destino y recupera el resultado si está bloqueado."""
        temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp.xlsx")
        try:
            workbook.save(temporary)
            for attempt in range(OUTPUT_REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary, path)
                    return path
                except OSError as exc:
                    # WinError 5 (acceso denegado) y 32 (archivo en uso) son
                    # habituales durante el cierre de Excel o la sincronización.
                    if getattr(exc, "winerror", None) not in {5, 32}:
                        raise
                    if attempt + 1 < OUTPUT_REPLACE_ATTEMPTS:
                        time.sleep(OUTPUT_REPLACE_DELAY_SECONDS)
            recovered = path.with_name(f"{path.stem}_recuperado_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.xlsx")
            try:
                os.replace(temporary, recovered)
            except OSError as exc:
                raise RuntimeError(
                    f"No se pudo sustituir {path.name} porque sigue bloqueado y tampoco se pudo conservar la copia temporal. "
                    f"Cierra el archivo en Excel y vuelve a intentarlo. Archivo temporal: {temporary}"
                ) from exc
            return recovered
        finally:
            workbook.close()
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
