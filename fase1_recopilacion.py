"""
FASE 1 - Recopilacion de partes mensuales

Requisitos:
    pip install pywin32 openpyxl
    Microsoft Excel instalado en Windows

Resumen:
    - Abre cada Excel sobre una copia temporal; no modifica el original.
    - Procesa Excel en paralelo con numero automatico y prudente de procesos.
    - Cada proceso usa su propia instancia de Microsoft Excel.
    - Desprotege hojas protegidas con la clave local de configuración.
    - Borra valores D5:AH2500 solo en la hoja del mes elegido, salvo la columna del dia elegido.
    - Recalcula de forma estricta para evitar perdidas de datos en CONTROL.
    - Extrae CONTROL directamente desde Excel COM, no desde cache de openpyxl.
    - Audita filas esperadas vs filas extraidas para detectar cualquier perdida.
    - La escritura del Excel final se hace solo en el proceso principal.
"""

from __future__ import annotations

import calendar
import os
import queue
import shutil
import tempfile
import time
import sys
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from multiprocessing import Manager, freeze_support
from pathlib import Path
from typing import Callable, Any

from core.config import get_excel_password
from core.exceptions import ProcessingCancelled

import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

# En PyInstaller debe ejecutarse antes de cualquier uso de multiprocessing.
freeze_support()

MONTH_SHEETS = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MONTH_LABELS = [m.upper() for m in MONTH_SHEETS]
DATA_FIRST_ROW = 4
CONTROL_SHEET = "CONTROL"
MONTHLY_CONTROL_SHEET = "Control 20_20"
CLEAR_FIRST_ROW = 5
CLEAR_LAST_ROW = 2500
CLEAR_FIRST_COL = 4   # D
CLEAR_LAST_COL = 34   # AH
MONTH_BLOCK_WIDTH_DEFAULT = 15
DEFAULT_MAX_WORKERS = 2
MAX_SAFE_WORKERS = 4
CONTROL_MAX_SCAN_ROW = 2500
PERSON_REQUIRED_COLUMNS = (8, 10, 11)  # H, J, K: APELLIDOS, NOMBRE y ALTA obligatorios. ALTA debe ser anterior a la fecha elegida
EMPLOYMENT_MODE_ACTIVE = "activos"
EMPLOYMENT_MODE_INACTIVE = "bajas"
PROCESS_MODE_DAILY = "diario"
PROCESS_MODE_MONTHLY = "mensual"

DEPARTMENT_ABBREVIATIONS = {
    "AUXILIARESSVO": "MV",
    "CANTIMPALOS": "SVC",
    "CASQUERIA": "MC",
    "CALIDAD": "CAL",
    "COMPRAS": "COMP",
    "CONGELADO": "C",
    "ENVASADO MANANA": "VM",
    "ENVASADO TARDE": "VT",
    "EXPEDICIONES": "X",
    "L1": "L1",
    "L2": "L2",
    "L3": "L3",
    "L5": "L5",
    "MANTENIMIENTO": "MTO",
    "MATANZA LIMPIA": "ML",
    "MATANZA SUCIA": "MS",
    "OFICINAS": "ADMON",
    "RRHH": "RRHH",
    "RT": "RT",
    "SECADEROS": "SV",
    "SKIN": "SK",
    "TIC": "TIC",
    "TIRSO": "TIR",
    "TREN ETIQUETADO": "TR",
}


def is_frozen_exe() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_parallel_available() -> bool:
    """Permite multiprocessing tambien en el EXE.

    La proteccion frente a procesos hijo de PyInstaller se hace con
    multiprocessing.freeze_support() antes de crear ventanas. Desactivar
    aqui el paralelismo hacia que el EXE procesara todos los archivos
    secuencialmente aunque el log anunciara varios procesos.
    """
    return True

# En datos sensibles prima la integridad. Esta opcion fuerza un recalculo completo
# del libro tras limpiar el dia/mes, que es mas fiel al proceso manual.
STRICT_FULL_RECALCULATION = True

ProgressCallback = Callable[[dict], None]
CancellationCheck = Callable[[], bool]


def _raise_if_cancelled(should_cancel: CancellationCheck | None) -> None:
    """Detiene el procesamiento en un punto seguro si se solicito cancelar."""
    if should_cancel and should_cancel():
        raise ProcessingCancelled("Cancelación solicitada por el usuario.")


def get_recommended_max_workers(file_count: int | None = None) -> int:
    """Devuelve un numero prudente de procesos para Excel COM."""
    cpu = os.cpu_count() or 2
    if cpu <= 4:
        workers = 2
    elif cpu <= 8:
        workers = 3
    else:
        workers = 4
    workers = max(1, min(workers, MAX_SAFE_WORKERS))
    if file_count is not None:
        workers = min(workers, max(1, int(file_count)))
    return workers


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def normalize_department_text(value) -> str:
    import unicodedata
    text = str(value or "").upper()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    keep = []
    for ch in text:
        keep.append(ch if ch.isalnum() else " ")
    return " ".join("".join(keep).split())


def department_abbreviation_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    normalized = normalize_department_text(stem)
    compact = normalized.replace(" ", "")
    # ML y MS deben prevalecer sobre cualquier abreviatura genérica que
    # aparezca en el nombre comercial del parte (por ejemplo, RT).
    for department_name, abbreviation in (
        ("MATANZA LIMPIA", "ML"),
        ("MATANZA SUCIA", "MS"),
    ):
        if normalize_department_text(department_name) in normalized:
            return abbreviation
        if abbreviation in normalized.split():
            return abbreviation
    # Primero coincidencias largas para evitar que L1/L2/L3/L5 coincidan dentro de otros nombres.
    for key in sorted(DEPARTMENT_ABBREVIATIONS, key=len, reverse=True):
        key_norm = normalize_department_text(key)
        key_compact = key_norm.replace(" ", "")
        if key_compact in compact or key_norm in normalized:
            return DEPARTMENT_ABBREVIATIONS[key]
    return ""


def is_blank(value) -> bool:
    return value is None or str(value).strip() == ""




def parse_excel_date(value) -> date | None:
    """Convierte fechas de Excel COM/openpyxl a date.

    Excel COM puede devolver fechas como datetime, date, numero serial o texto.
    Devuelve None si no puede interpretarse con seguridad.
    """
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Sistema de fechas 1900 de Excel. Excel incluye el falso 29/02/1900;
        # usando 1899-12-30 se alinea con los seriales habituales de COM.
        try:
            return (date(1899, 12, 30) + timedelta(days=int(value))).date() if isinstance(date(1899, 12, 30) + timedelta(days=int(value)), datetime) else date(1899, 12, 30) + timedelta(days=int(value))
        except Exception:
            return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except Exception:
            pass
    return None


def excel_col_letter(col: int) -> str:
    result = ""
    while col:
        col, rem = divmod(col - 1, 26)
        result = chr(65 + rem) + result
    return result


EXCEL_ERROR_CODES = {
    2000: "#NULL!",
    2007: "#DIV/0!",
    2015: "#VALUE!",
    2023: "#REF!",
    2029: "#NAME?",
    2036: "#NUM!",
    2042: "#N/A",
}


def _normalize_excel_com_value(value: Any) -> Any:
    """Convierte los codigos CVErr de COM al error Excel visible correspondiente.

    Excel COM devuelve, por ejemplo, ``#N/A`` como el entero firmado
    ``-2146826246``. Si se escribe ese entero en la recopilacion parece un
    dato numerico real, cuando en realidad es un error de formula de origen.
    """
    if isinstance(value, int) and value < 0:
        excel_error_code = value & 0xFFFF
        return EXCEL_ERROR_CODES.get(excel_error_code, value)
    return value


def _range_to_2d_list(value: Any) -> list[list[Any]]:
    """Convierte Range.Value/Value2 de COM en lista 2D estable y legible."""
    if value is None:
        return []
    if not isinstance(value, tuple):
        return [[_normalize_excel_com_value(value)]]
    if value and not isinstance(value[0], tuple):
        return [[_normalize_excel_com_value(item) for item in value]]
    return [[_normalize_excel_com_value(item) for item in row] for row in value]


@dataclass
class ExtractedRow:
    source_file: str
    worker_values: list
    month_values: list
    source_row: int | None = None


@dataclass
class ProcessingResult:
    index: int
    source_file: str
    rows: list[ExtractedRow]
    worker_headers: list
    month_headers: list
    last_person_row: int
    month_start_col: int
    month_width: int
    elapsed_seconds: float
    audit: dict = field(default_factory=dict)
    worker_audit_rows: list[dict] = field(default_factory=list)


def _emit(progress_queue, event: str, index: int, file_path: str, message: str, **extra) -> None:
    if progress_queue is None:
        return
    payload = {
        "event": event,
        "index": index,
        "file": Path(file_path).name,
        "path": file_path,
        "message": message,
        "time": time.strftime("%H:%M:%S"),
        "pid": os.getpid(),
    }
    payload.update(extra)
    try:
        progress_queue.put(payload)
    except Exception:
        pass


def _clear_non_selected_day_in_month_sheet(ws, selected_day: int) -> int:
    """Limpia D5:AH2500 en la hoja activa salvo la columna del dia elegido."""
    day_col = CLEAR_FIRST_COL + selected_day - 1
    cleared_cells = 0
    row_count = CLEAR_LAST_ROW - CLEAR_FIRST_ROW + 1

    ranges_to_clear = []
    if day_col > CLEAR_FIRST_COL:
        ranges_to_clear.append((CLEAR_FIRST_COL, day_col - 1))
    if day_col < CLEAR_LAST_COL:
        ranges_to_clear.append((day_col + 1, CLEAR_LAST_COL))

    for first_col, last_col in ranges_to_clear:
        first_letter = excel_col_letter(first_col)
        last_letter = excel_col_letter(last_col)
        ws.Range(f"{first_letter}{CLEAR_FIRST_ROW}:{last_letter}{CLEAR_LAST_ROW}").ClearContents()
        cleared_cells += (last_col - first_col + 1) * row_count

    return cleared_cells



def get_previous_month(year: int, month: int) -> tuple[int, int]:
    """Devuelve (anio, mes) del mes anterior al mes indicado."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def get_next_month(year: int, month: int) -> tuple[int, int]:
    """Devuelve (anio, mes) del mes posterior al mes indicado."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def get_monthly_control_month_label(selected_date_obj: date) -> str:
    """Devuelve el bloque de ``CONTROL 20_20`` que corresponde al periodo activo.

    Los bloques mensuales de CONTROL 20_20 se etiquetan por el mes en el que
    termina el ciclo 21_20. Por ejemplo, el bloque JULIO suma 21/06-20/07 y
    el bloque AGOSTO suma 21/07-20/08. Por ello, desde el dia 21 inclusive
    se debe consultar el bloque del mes siguiente, aunque la fecha elegida
    siga perteneciendo al mes actual.
    """
    if selected_date_obj.day >= 21:
        _year, month = get_next_month(selected_date_obj.year, selected_date_obj.month)
        return MONTH_LABELS[month - 1]
    return MONTH_LABELS[selected_date_obj.month - 1]


def _clear_columns_in_month_sheet(ws, first_day: int, last_day: int) -> int:
    """Limpia los dias indicados (ambos incluidos) en D5:AH2500."""
    first_day = max(1, int(first_day))
    last_day = min(31, int(last_day))
    if first_day > last_day:
        return 0
    first_col = CLEAR_FIRST_COL + first_day - 1
    last_col = CLEAR_FIRST_COL + last_day - 1
    first_col = max(CLEAR_FIRST_COL, first_col)
    last_col = min(CLEAR_LAST_COL, last_col)
    if first_col > last_col:
        return 0
    first_letter = excel_col_letter(first_col)
    last_letter = excel_col_letter(last_col)
    ws.Range(f"{first_letter}{CLEAR_FIRST_ROW}:{last_letter}{CLEAR_LAST_ROW}").ClearContents()
    return (last_col - first_col + 1) * (CLEAR_LAST_ROW - CLEAR_FIRST_ROW + 1)


def _clear_monthly_period(wb, selected_date_obj: date) -> tuple[int, list[str]]:
    """
    Prepara el periodo mensual 20_20 conservando solo el tramo necesario.

    Regla aplicada:
    - Si la fecha elegida es dia 21 o posterior, se conserva del dia 21 del
      mismo mes hasta la fecha elegida. Ej.: 25/05 -> 21/05 a 25/05. Tambien
      se limpian los dias 1-20 del mes siguiente, porque el bloque de CONTROL
      20_20 que representa ese periodo se etiqueta con dicho mes siguiente.
    - Si la fecha elegida es anterior al dia 21, se conserva del dia 21 del
      mes anterior hasta la fecha elegida. Ej.: 12/06 -> 21/05 a 12/06.
    """
    cleared_cells = 0
    touched: list[str] = []
    previous_year, previous_month = get_previous_month(selected_date_obj.year, selected_date_obj.month)
    previous_sheet_name = MONTH_SHEETS[previous_month - 1]
    selected_sheet_name = MONTH_SHEETS[selected_date_obj.month - 1]
    _next_year, next_month = get_next_month(selected_date_obj.year, selected_date_obj.month)
    next_sheet_name = MONTH_SHEETS[next_month - 1]

    if selected_date_obj.day >= 21:
        # El bloque del mes siguiente suma seleccionado:21-31 + siguiente:1-20.
        # Solo debe quedar 21-dia elegido del mes seleccionado.
        sheet_ranges = (
            (previous_sheet_name, [(1, 31)]),
            (selected_sheet_name, [(1, 20), (selected_date_obj.day + 1, 31)]),
            (next_sheet_name, [(1, 20)]),
        )
    else:
        # Debe quedar 21-fin del mes anterior y 1-dia elegido del mes seleccionado.
        sheet_ranges = (
            (previous_sheet_name, [(1, 20)]),
            (selected_sheet_name, [(selected_date_obj.day + 1, 31)]),
        )

    for sheet_name, ranges in sheet_ranges:
        try:
            ws = wb.Worksheets(sheet_name)
        except Exception as exc:
            raise RuntimeError(f"No existe la hoja del periodo mensual: {sheet_name}") from exc
        try:
            ws.Unprotect(get_excel_password())
        except Exception:
            pass
        try:
            ws.DisplayPageBreaks = False
        except Exception:
            pass
        for first_day, last_day in ranges:
            cleared = _clear_columns_in_month_sheet(ws, first_day, last_day)
            cleared_cells += cleared
            if cleared:
                touched.append(f"{sheet_name} dias {first_day}-{last_day}")
    return cleared_cells, touched

def _find_control_month_block(control, month_label: str) -> tuple[int, int, list, list[tuple[int, str]]]:
    xl_to_left = -4159
    last_col = control.Cells(2, control.Columns.Count).End(xl_to_left).Column
    last_col = max(last_col, 12)
    row2 = _range_to_2d_list(control.Range(control.Cells(2, 1), control.Cells(2, last_col)).Value2)
    row2_values = row2[0] if row2 else []

    month_positions: list[tuple[int, str]] = []
    for idx, value in enumerate(row2_values, start=1):
        label = normalize_text(value)
        if label in MONTH_LABELS:
            month_positions.append((idx, label))

    for pos, (col, label) in enumerate(month_positions):
        if label == month_label:
            if pos + 1 < len(month_positions):
                width = month_positions[pos + 1][0] - col
            else:
                width = MONTH_BLOCK_WIDTH_DEFAULT
            return col, width, row2_values, month_positions

    raise RuntimeError(f"No se encontro el mes {month_label} en la fila 2 de CONTROL")


def _find_baja_column(control) -> int:
    headers = _range_to_2d_list(control.Range("A3:L3").Value2)
    header_values = headers[0] if headers else []
    for idx, value in enumerate(header_values, start=1):
        if normalize_text(value) == "BAJA":
            return idx
    return 12  # fallback historico: L


def _find_last_person_row_from_control(control) -> tuple[int, int, list[list[Any]], list[int], list[str]]:
    """Detecta trabajadores reales sin depender de una sola columna.

    Motivo: en algunos partes hay filas posteriores con formulas, numeracion o
    totales parciales en A:F, pero sin trabajador real. Si se considera A:F como
    identificador, aparecen lineas en blanco en la salida.

    Regla robusta actual de candidatura: una fila solo se revisa como posible
    trabajador si tiene informados los campos obligatorios de CONTROL:
        - columna H: APELLIDOS / identificador de apellidos
        - columna J: NOMBRE
        - columna K: ALTA

    La inclusion final de activos exige ademas que ALTA sea anterior a la fecha
    elegida y que BAJA este vacia o sea posterior a esa fecha. No se usa A:F
    porque puede contener numeracion, tiempos o formulas auxiliares. No se usa
    L para decidir si existe trabajador: solo para decidir si estaba activo en
    la fecha seleccionada.
    """
    used_last = control.UsedRange.Row + control.UsedRange.Rows.Count - 1
    scan_until = max(CONTROL_MAX_SCAN_ROW, used_last, DATA_FIRST_ROW)

    data = _range_to_2d_list(
        control.Range(control.Cells(DATA_FIRST_ROW, 1), control.Cells(scan_until, 12)).Value2
    )

    person_offsets: list[int] = []
    warnings: list[str] = []
    ignored_non_identity_rows = 0
    for offset, row in enumerate(data):
        # Normaliza longitud A:L
        if len(row) < 12:
            row.extend([None] * (12 - len(row)))

        apellidos_value = row[7] if len(row) > 7 else None # H
        nombre_value = row[9] if len(row) > 9 else None    # J
        alta_value = row[10] if len(row) > 10 else None    # K

        # Solo se considera trabajador real si tiene APELLIDOS, NOMBRE y ALTA.
        # Esto evita incluir filas con formulas, numeracion o datos auxiliares,
        # y cumple la regla funcional: sin estos campos no interesa incluirla.
        has_required_worker_fields = (
            (not is_blank(apellidos_value))
            and (not is_blank(nombre_value))
            and (not is_blank(alta_value))
        )

        has_any_aux_data = any(not is_blank(row[i]) for i in range(min(12, len(row))))

        if has_required_worker_fields:
            person_offsets.append(offset)
            absolute_row = DATA_FIRST_ROW + offset
            if is_blank(row[5]):
                warnings.append(
                    f"Fila {absolute_row}: F vacia, pero se conserva porque tiene APELLIDOS+NOMBRE+ALTA"
                )
        elif has_any_aux_data:
            ignored_non_identity_rows += 1

    if ignored_non_identity_rows:
        warnings.append(
            f"Filas con datos pero sin APELLIDOS+NOMBRE+ALTA ignoradas: {ignored_non_identity_rows}"
        )

    if not person_offsets:
        return DATA_FIRST_ROW - 1, scan_until, data, [], warnings

    last_person_row = DATA_FIRST_ROW + max(person_offsets)
    return last_person_row, scan_until, data, person_offsets, warnings

def _prepare_and_extract_with_excel(
    temp_path: Path,
    source_name: str,
    selected_day: int,
    selected_month: int,
    selected_date_obj: date,
    employment_mode: str,
    process_mode: str,
    progress_queue,
    index: int,
    source_path: str,
    should_cancel: CancellationCheck | None = None,
) -> tuple[list[ExtractedRow], list, list, int, int, int, dict, list[dict]]:
    """Procesa y extrae usando Excel COM para evitar perdidas por cache de openpyxl.

    Esta es la parte critica de integridad: despues de limpiar y recalcular, lee
    los bloques A:L y mes seleccionado directamente desde Excel en memoria.
    """
    import pythoncom
    import win32com.client as win32

    selected_sheet_name = MONTH_SHEETS[selected_month - 1]
    selected_month_label = MONTH_LABELS[selected_month - 1]
    excel = None
    wb = None
    pythoncom.CoInitialize()
    try:
        _raise_if_cancelled(should_cancel)
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.EnableEvents = False
        excel.ScreenUpdating = False
        try:
            excel.AskToUpdateLinks = False
        except Exception:
            pass
        # Evita elementos visuales molestos de Excel durante la automatizacion
        # (incluido el icono flotante de Analisis rapido cuando Excel decide mostrarlo).
        for command_bar_name in ("Quick Analysis", "Quick Analysis Bar"):
            try:
                excel.CommandBars(command_bar_name).Enabled = False
            except Exception:
                pass
        try:
            excel.DisplayStatusBar = False
        except Exception:
            pass
        try:
            excel.Calculation = -4135  # xlCalculationManual
        except Exception:
            pass

        _emit(progress_queue, "stage", index, source_path, "Abriendo copia temporal con Excel", progress_units=1)
        wb = excel.Workbooks.Open(str(temp_path), UpdateLinks=0, ReadOnly=False)
        _raise_if_cancelled(should_cancel)

        if process_mode == PROCESS_MODE_MONTHLY:
            _emit(progress_queue, "stage", index, source_path, "Limpiando periodo mensual 20_20", progress_units=1)
            cleared_cells, cleared_ranges = _clear_monthly_period(wb, selected_date_obj)
            control_sheet_name = MONTHLY_CONTROL_SHEET
            control_month_label = get_monthly_control_month_label(selected_date_obj)
        else:
            _emit(progress_queue, "stage", index, source_path, f"Limpiando solo la hoja {selected_sheet_name}", sheet=selected_sheet_name, progress_units=1)
            try:
                ws = wb.Worksheets(selected_sheet_name)
            except Exception as exc:
                raise RuntimeError(f"No existe la hoja del mes seleccionado: {selected_sheet_name}") from exc

            try:
                ws.Unprotect(get_excel_password())
            except Exception:
                pass
            try:
                ws.DisplayPageBreaks = False
            except Exception:
                pass
            cleared_cells = _clear_non_selected_day_in_month_sheet(ws, selected_day)
            cleared_ranges = [f"{selected_sheet_name}: se conserva dia {selected_day}"]
            control_sheet_name = CONTROL_SHEET
            control_month_label = selected_month_label

        _raise_if_cancelled(should_cancel)

        _emit(progress_queue, "stage", index, source_path, f"Preparando hoja {control_sheet_name}", progress_units=1)
        try:
            control = wb.Worksheets(control_sheet_name)
        except Exception as exc:
            raise RuntimeError(f"No existe la hoja {control_sheet_name!r}") from exc
        try:
            control.Unprotect(get_excel_password())
        except Exception:
            pass

        _emit(progress_queue, "stage", index, source_path, "Recalculando libro completo para asegurar CONTROL", cleared_cells=cleared_cells, progress_units=1)
        try:
            excel.Calculation = -4105  # xlCalculationAutomatic
        except Exception:
            pass
        if STRICT_FULL_RECALCULATION:
            try:
                excel.CalculateFullRebuild()
            except Exception:
                excel.CalculateFull()
        else:
            try:
                if process_mode == PROCESS_MODE_DAILY:
                    ws.Calculate()
                control.Calculate()
            except Exception:
                excel.CalculateFull()
        try:
            excel.CalculateUntilAsyncQueriesDone()
        except Exception:
            pass

        # Espera prudente a que Excel termine el calculo. xlDone = 0.
        for _ in range(240):
            _raise_if_cancelled(should_cancel)
            try:
                if excel.CalculationState == 0:
                    break
            except Exception:
                break
            time.sleep(0.25)

        _raise_if_cancelled(should_cancel)
        _emit(progress_queue, "stage", index, source_path, "Localizando bloque mensual y filas de CONTROL", progress_units=1)
        month_start, month_width, row2_values, month_positions = _find_control_month_block(control, control_month_label)
        baja_col = _find_baja_column(control)
        last_person_row, scanned_until, worker_scan_data, person_offsets, detection_warnings = _find_last_person_row_from_control(control)
        if last_person_row < DATA_FIRST_ROW or not person_offsets:
            raise RuntimeError("No se encontraron registros de personas en CONTROL")

        _emit(progress_queue, "stage", index, source_path, "Leyendo CONTROL en bloques", last_person_row=last_person_row, progress_units=1)
        worker_headers_2d = _range_to_2d_list(control.Range("A3:L3").Value2)
        worker_headers = worker_headers_2d[0] if worker_headers_2d else []
        month_headers_2d = _range_to_2d_list(control.Range(control.Cells(3, month_start), control.Cells(3, month_start + month_width - 1)).Value2)
        month_headers = month_headers_2d[0] if month_headers_2d else []

        # Se lee el bloque mensual hasta la misma cota que A:L. A:L ya se ha leido
        # durante la deteccion robusta para evitar una segunda lectura COM costosa.
        month_scan_data = _range_to_2d_list(control.Range(control.Cells(DATA_FIRST_ROW, month_start), control.Cells(scanned_until, month_start + month_width - 1)).Value2)

        mode_label = "trabajadores activos" if employment_mode == EMPLOYMENT_MODE_ACTIVE else "trabajadores de baja"
        _emit(progress_queue, "stage", index, source_path, f"Filtrando {mode_label} y auditando trabajadores", baja_col=baja_col, progress_units=1)
        extracted: list[ExtractedRow] = []
        worker_audit_rows: list[dict] = []
        expected_included_rows = 0
        skipped_rows = 0
        blank_f_inside_range = 0
        audit_warnings: list[str] = list(detection_warnings)

        for offset in person_offsets:
            if offset % 50 == 0:
                _raise_if_cancelled(should_cancel)
            absolute_row = DATA_FIRST_ROW + offset
            worker_values = worker_scan_data[offset] if offset < len(worker_scan_data) else []
            if len(worker_values) < 12:
                worker_values = list(worker_values) + [None] * (12 - len(worker_values))
            else:
                worker_values = list(worker_values[:12])

            f_value = worker_values[5] if len(worker_values) >= 6 else None
            if is_blank(f_value):
                blank_f_inside_range += 1

            baja_value = worker_values[baja_col - 1] if len(worker_values) >= baja_col else None
            baja_date = parse_excel_date(baja_value)
            alta_value = worker_values[10] if len(worker_values) > 10 else None
            alta_date = parse_excel_date(alta_value)
            mv = month_scan_data[offset] if offset < len(month_scan_data) else []
            if len(mv) < month_width:
                mv = list(mv) + [None] * (month_width - len(mv))
            else:
                mv = list(mv[:month_width])

            worker_key = " | ".join(str(v) for v in [
                worker_values[6] if len(worker_values) > 6 else None,
                worker_values[7] if len(worker_values) > 7 else None,
                worker_values[8] if len(worker_values) > 8 else None,
                worker_values[9] if len(worker_values) > 9 else None,
                worker_values[10] if len(worker_values) > 10 else None,
            ] if not is_blank(v))

            if alta_date is None:
                skipped_rows += 1
                decision = "EXCLUIDO"
                reason = f"ALTA no interpretable: {alta_value}"
            elif alta_date >= selected_date_obj:
                skipped_rows += 1
                decision = "EXCLUIDO"
                reason = f"ALTA no anterior a fecha seleccionada: {alta_date.strftime('%d/%m/%Y')} >= {selected_date_obj.strftime('%d/%m/%Y')}"
            elif employment_mode == EMPLOYMENT_MODE_ACTIVE:
                if is_blank(baja_value):
                    expected_included_rows += 1
                    extracted.append(ExtractedRow(source_name, worker_values, mv, source_row=absolute_row))
                    decision = "INCLUIDO"
                    reason = "ACTIVO: APELLIDOS+NOMBRE+ALTA OK, ALTA anterior y BAJA vacia"
                elif baja_date and baja_date >= selected_date_obj:
                    expected_included_rows += 1
                    extracted.append(ExtractedRow(source_name, worker_values, mv, source_row=absolute_row))
                    decision = "INCLUIDO"
                    reason = f"ACTIVO EN FECHA: BAJA igual o posterior a fecha seleccionada ({baja_date.strftime('%d/%m/%Y')} >= {selected_date_obj.strftime('%d/%m/%Y')})"
                else:
                    skipped_rows += 1
                    decision = "EXCLUIDO"
                    if baja_date:
                        reason = f"BAJA anterior a fecha seleccionada: {baja_date.strftime('%d/%m/%Y')} < {selected_date_obj.strftime('%d/%m/%Y')}"
                    else:
                        reason = f"BAJA informada pero no interpretable como posterior a la fecha seleccionada: {baja_value}"
            else:
                skipped_rows += 1
                decision = "EXCLUIDO"
                reason = "Modo trabajadores de baja pendiente de implementar; no se extraen registros"

            worker_audit_rows.append({
                "source_file": source_name,
                "source_row": absolute_row,
                "decision": decision,
                "reason": reason,
                "baja_value": baja_value,
                "baja_interpretada": baja_date.strftime("%d/%m/%Y") if baja_date else "",
                "worker_key": worker_key,
                "alta_interpretada": alta_date.strftime("%d/%m/%Y") if alta_date else "",
                "worker_values": worker_values,
            })

        total_person_rows_detected = len(person_offsets)
        audit = {
            "source_file": source_name,
            "selected_month": control_month_label,
            "selected_calendar_month": selected_month_label,
            "selected_day": selected_day,
            "selected_date": selected_date_obj.strftime("%d/%m/%Y"),
            "cleared_cells": cleared_cells,
            "last_person_row": last_person_row,
            "scanned_until_row": scanned_until,
            "total_person_rows": total_person_rows_detected,
            "baja_column": baja_col,
            "employment_mode": employment_mode,
            "process_mode": process_mode,
            "control_sheet": control_sheet_name,
            "cleared_ranges": "; ".join(cleared_ranges),
            "expected_included_rows": expected_included_rows,
            "expected_blank_baja_rows": expected_included_rows,
            "extracted_rows": len(extracted),
            "skipped_rows": skipped_rows,
            "skipped_baja_rows": skipped_rows,
            "blank_f_inside_range": blank_f_inside_range,
            "identity_columns_used": "H:J:K obligatorias (APELLIDOS + NOMBRE + ALTA), ALTA anterior a fecha seleccionada y activos = BAJA vacia o BAJA igual/posterior a fecha",
            "month_start_col": month_start,
            "month_width": month_width,
            "month_positions": "; ".join(f"{label}:{col}" for col, label in month_positions),
            "warnings": " | ".join(audit_warnings),
            "status": "OK",
        }

        if expected_included_rows != len(extracted):
            audit["status"] = "ERROR"
            raise RuntimeError(
                f"Auditoria fallida en {source_name}: se esperaban {expected_included_rows} filas incluidas "
                f"y se extrajeron {len(extracted)}"
            )

        _emit(progress_queue, "audit", index, source_path, "Auditoria OK", rows=len(extracted), expected=expected_included_rows)
        return extracted, worker_headers, month_headers, last_person_row, month_start, month_width, audit, worker_audit_rows
    finally:
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:
                pass
        if excel is not None:
            try:
                excel.DisplayAlerts = False
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def process_one_file_worker(
    index: int,
    file_path_str: str,
    selected_date_iso: str,
    employment_mode: str = EMPLOYMENT_MODE_ACTIVE,
    process_mode: str = PROCESS_MODE_DAILY,
    progress_queue=None,
    should_cancel: CancellationCheck | None = None,
) -> ProcessingResult:
    start = time.time()
    file_path = Path(file_path_str)
    selected_date = datetime.fromisoformat(selected_date_iso)

    _raise_if_cancelled(should_cancel)
    _emit(progress_queue, "start", index, str(file_path), "Iniciando procesamiento")
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir) / file_path.name
        _emit(progress_queue, "stage", index, str(file_path), "Copiando archivo a temporal", progress_units=1)
        shutil.copy2(file_path, temp_path)
        _raise_if_cancelled(should_cancel)

        rows, worker_headers, month_headers, last_row, month_start, month_width, audit, worker_audit_rows = _prepare_and_extract_with_excel(
            temp_path=temp_path,
            source_name=file_path.name,
            selected_day=selected_date.day,
            selected_month=selected_date.month,
            selected_date_obj=selected_date.date(),
            employment_mode=employment_mode,
            process_mode=process_mode,
            progress_queue=progress_queue,
            index=index,
            source_path=str(file_path),
            should_cancel=should_cancel,
        )

    elapsed = time.time() - start
    audit["elapsed_seconds"] = round(elapsed, 1)
    _emit(
        progress_queue,
        "done",
        index,
        str(file_path),
        f"Finalizado: {len(rows)} registros utiles",
        rows=len(rows),
        last_person_row=last_row,
        month_start_col=month_start,
        month_width=month_width,
        elapsed_seconds=round(elapsed, 1),
    )
    return ProcessingResult(
        index=index,
        source_file=file_path.name,
        rows=rows,
        worker_headers=worker_headers,
        month_headers=month_headers,
        last_person_row=last_row,
        month_start_col=month_start,
        month_width=month_width,
        elapsed_seconds=elapsed,
        audit=audit,
        worker_audit_rows=worker_audit_rows,
    )


class ExcelCollector:
    def __init__(self, selected_date: datetime, output_path: Path, max_workers: int | str = DEFAULT_MAX_WORKERS, employment_mode: str = EMPLOYMENT_MODE_ACTIVE, process_mode: str = PROCESS_MODE_DAILY):
        self.selected_date = selected_date
        self.output_path = Path(output_path)
        if employment_mode not in (EMPLOYMENT_MODE_ACTIVE, EMPLOYMENT_MODE_INACTIVE):
            raise ValueError(f"Modo de trabajadores no valido: {employment_mode}")
        self.employment_mode = employment_mode
        if process_mode not in (PROCESS_MODE_DAILY, PROCESS_MODE_MONTHLY):
            raise ValueError(f"Modo de proceso no valido: {process_mode}")
        self.process_mode = process_mode
        if max_workers in (None, 0, "auto"):
            self.max_workers = get_recommended_max_workers()
        else:
            self.max_workers = max(1, int(max_workers))
        self.max_workers = min(self.max_workers, MAX_SAFE_WORKERS)
        self.month_label = (
            get_monthly_control_month_label(selected_date.date())
            if self.process_mode == PROCESS_MODE_MONTHLY
            else MONTH_LABELS[selected_date.month - 1]
        )
        self.rows: list[ExtractedRow] = []
        self.worker_headers: list = []
        self.month_headers: list = []
        self.results: list[ProcessingResult] = []

    def run(
        self,
        files: list[Path],
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> None:
        files = [Path(p) for p in files]
        if not files:
            raise ValueError("No hay archivos para procesar")
        _raise_if_cancelled(should_cancel)

        self.max_workers = min(self.max_workers, get_recommended_max_workers(len(files)))
        total_units = len(files) * 9 + 1

        if progress_callback:
            progress_callback({
                "event": "overall_start",
                "message": f"Procesando {len(files)} archivo(s) con hasta {min(self.max_workers, len(files))} proceso(s)",
                "total_files": len(files),
                "total_units": total_units,
                "workers": min(self.max_workers, len(files)),
            })

        # En el ejecutable Windows con interfaz grafica, ProcessPool puede crear
        # procesos hijos que vuelven a levantar el menu o quedan bloqueados antes de
        # enviar progreso. Para preservar estabilidad se usa ejecucion secuencial
        # dentro del hilo de trabajo; al ejecutar desde Python sigue disponible el
        # paralelismo original.
        if self.max_workers <= 1 or len(files) == 1 or not is_parallel_available():
            self.results = self._run_serial(files, progress_callback, should_cancel)
        else:
            self.results = self._run_parallel(files, progress_callback, should_cancel)

        _raise_if_cancelled(should_cancel)

        self.results.sort(key=lambda r: r.index)
        self.rows = []
        for result in self.results:
            if not self.worker_headers and result.worker_headers:
                self.worker_headers = result.worker_headers
            if not self.month_headers and result.month_headers:
                self.month_headers = result.month_headers
            self.rows.extend(result.rows)

        total_audit_rows = sum(int(r.audit.get("extracted_rows", len(r.rows))) for r in self.results)
        if total_audit_rows != len(self.rows):
            raise RuntimeError(f"Auditoria global fallida: resultados={len(self.rows)}, auditoria={total_audit_rows}")

        if progress_callback:
            progress_callback({"event": "writing", "message": "Escribiendo archivo final", "rows": len(self.rows), "progress_units": 1})
        _raise_if_cancelled(should_cancel)
        self._write_output()
        if progress_callback:
            progress_callback({"event": "overall_done", "message": "Archivo final generado", "rows": len(self.rows)})

    def _run_serial(
        self,
        files: list[Path],
        progress_callback: ProgressCallback | None,
        should_cancel: CancellationCheck | None,
    ) -> list[ProcessingResult]:
        class DirectQueue:
            def put(self, item):
                if progress_callback:
                    progress_callback(item)

        results = []
        for index, path in enumerate(files):
            _raise_if_cancelled(should_cancel)
            results.append(process_one_file_worker(
                index,
                str(path),
                self.selected_date.isoformat(),
                self.employment_mode,
                self.process_mode,
                DirectQueue(),
                should_cancel,
            ))
            if progress_callback:
                progress_callback({"event": "file_completed", "completed_files": len(results), "total_files": len(files), "progress_units": 0})
        return results

    def _run_parallel(
        self,
        files: list[Path],
        progress_callback: ProgressCallback | None,
        should_cancel: CancellationCheck | None,
    ) -> list[ProcessingResult]:
        results: list[ProcessingResult] = []
        with Manager() as manager:
            progress_queue = manager.Queue()
            cancellation_event = manager.Event()
            with ProcessPoolExecutor(max_workers=min(self.max_workers, len(files))) as executor:
                future_map = {
                    executor.submit(
                        process_one_file_worker,
                        index,
                        str(path),
                        self.selected_date.isoformat(),
                        self.employment_mode,
                        self.process_mode,
                        progress_queue,
                        cancellation_event.is_set,
                    ): path
                    for index, path in enumerate(files)
                }
                pending = set(future_map.keys())
                completed_files = 0
                cancellation_requested = False
                while pending:
                    if should_cancel and should_cancel():
                        cancellation_requested = True
                        cancellation_event.set()
                    done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                    self._drain_progress_queue(progress_queue, progress_callback)
                    for future in done:
                        path = future_map[future]
                        try:
                            result = future.result()
                        except ProcessingCancelled:
                            if cancellation_requested:
                                continue
                            raise
                        except Exception as exc:
                            for other in pending:
                                other.cancel()
                            raise RuntimeError(f"Error procesando {path.name}: {exc}") from exc
                        results.append(result)
                        completed_files += 1
                        if progress_callback:
                            progress_callback({
                                "event": "file_completed",
                                "file": path.name,
                                "completed_files": completed_files,
                                "total_files": len(files),
                                "rows": len(result.rows),
                                "progress_units": 0,
                            })
                self._drain_progress_queue(progress_queue, progress_callback)
                if cancellation_requested:
                    raise ProcessingCancelled("Cancelación solicitada por el usuario.")
        return results

    @staticmethod
    def _drain_progress_queue(progress_queue, progress_callback: ProgressCallback | None) -> None:
        if not progress_callback:
            return
        while True:
            try:
                progress_callback(progress_queue.get_nowait())
            except queue.Empty:
                break
            except Exception:
                break

    def _write_output(self) -> None:
        out = openpyxl.Workbook()
        ws = out.active
        ws.title = "Recopilacion"

        headers = [
            "Fecha",
            "Departamento",
        ] + self.worker_headers + [f"{self.month_label} - {h or ''}" for h in self.month_headers]
        ws.append(headers)

        for item in self.rows:
            department = department_abbreviation_from_filename(item.source_file)
            ws.append([self.selected_date.date(), department] + item.worker_values + item.month_values)

        self._apply_main_sheet_format(ws)

        audit_ws = out.create_sheet("Auditoria")
        audit_headers = [
            "Archivo", "Estado", "Proceso", "Modo", "Hoja control", "Rangos limpiados", "Mes", "Dia", "Fecha seleccionada", "Ultima fila persona", "Filas persona",
            "Filas esperadas incluidas", "Filas extraidas", "Filas omitidas",
            "Columna BAJA", "Columnas identidad", "Inicio bloque mes", "Columnas bloque mes", "Celdas limpiadas",
            "Escaneado hasta fila", "Segundos", "Posiciones meses", "Avisos",
        ]
        audit_ws.append(audit_headers)
        for result in self.results:
            a = result.audit or {}
            audit_ws.append([
                result.source_file,
                a.get("status", "OK"),
                a.get("process_mode", self.process_mode),
                a.get("employment_mode", self.employment_mode),
                a.get("control_sheet", ""),
                a.get("cleared_ranges", ""),
                a.get("selected_month", self.month_label),
                a.get("selected_day", self.selected_date.day),
                a.get("selected_date", self.selected_date.strftime("%d/%m/%Y")),
                a.get("last_person_row", result.last_person_row),
                a.get("total_person_rows", ""),
                a.get("expected_included_rows", a.get("expected_blank_baja_rows", len(result.rows))),
                a.get("extracted_rows", len(result.rows)),
                a.get("skipped_rows", a.get("skipped_baja_rows", "")),
                a.get("baja_column", ""),
                a.get("identity_columns_used", "H:J:K obligatorias (APELLIDOS + NOMBRE + ALTA), ALTA anterior y activos = BAJA vacia o igual/posterior"),
                a.get("month_start_col", result.month_start_col),
                a.get("month_width", result.month_width),
                a.get("cleared_cells", ""),
                a.get("scanned_until_row", ""),
                a.get("elapsed_seconds", round(result.elapsed_seconds, 1)),
                a.get("month_positions", ""),
                a.get("warnings", ""),
            ])
        self._apply_aux_sheet_format(audit_ws)

        worker_audit_ws = out.create_sheet("Trabajadores Auditoria")
        worker_audit_headers = [
            "Archivo", "Fila CONTROL", "Decision", "Motivo", "Valor BAJA", "Fecha BAJA interpretada", "Fecha ALTA interpretada", "Clave trabajador"
        ] + [str(h or f"Campo {i}") for i, h in enumerate(self.worker_headers, start=1)]
        worker_audit_ws.append(worker_audit_headers)
        for result in self.results:
            for wa in result.worker_audit_rows:
                worker_audit_ws.append([
                    wa.get("source_file", result.source_file),
                    wa.get("source_row", ""),
                    wa.get("decision", ""),
                    wa.get("reason", ""),
                    wa.get("baja_value", ""),
                    wa.get("baja_interpretada", ""),
                    wa.get("alta_interpretada", ""),
                    wa.get("worker_key", ""),
                ] + list(wa.get("worker_values", [])))
        self._apply_aux_sheet_format(worker_audit_ws)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.output_path.stem}.",
            suffix=self.output_path.suffix,
            dir=self.output_path.parent,
        )
        os.close(descriptor)
        temporary_output = Path(temporary_name)
        try:
            out.save(temporary_output)
            os.replace(temporary_output, self.output_path)
        finally:
            if temporary_output.exists():
                try:
                    temporary_output.unlink()
                except OSError:
                    pass

    def _apply_main_sheet_format(self, ws) -> None:
        primary = "003B8E"
        red = "E31B1B"
        light = "EAF2FF"
        thin = Side(style="thin", color="DCE3F0")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = PatternFill("solid", fgColor=primary)
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        ws.row_dimensions[1].height = 24

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center")
            row[0].number_format = "dd/mm/yyyy"

        # Formatos solicitados sobre columnas fijas del Excel final.
        for cell in ws["F"][1:]:
            cell.number_format = "hh:mm"
        for col in ("L", "M"):
            for cell in ws[col][1:]:
                cell.number_format = "dd/mm/yyyy"

        # Resalta las columnas nuevas de guia funcional.
        for col in (1, 2):
            for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2, max_row=ws.max_row):
                for item in cell:
                    item.fill = PatternFill("solid", fgColor=light)

        widths = {"A": 12, "B": 15, "C": 28, "F": 12, "L": 13, "M": 13}
        for column_cells in ws.columns:
            letter = get_column_letter(column_cells[0].column)
            max_len = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=0)
            ws.column_dimensions[letter].width = widths.get(letter, min(max(max_len + 2, 10), 35))

        # Banda roja inferior del bloque de encabezados para mantener la identidad visual del proyecto.
        ws.insert_rows(1)
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col)
            cell.fill = PatternFill("solid", fgColor=red)
        ws.row_dimensions[1].height = 5
        ws.freeze_panes = "A3"
        ws.auto_filter.ref = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"

    def _apply_aux_sheet_format(self, ws) -> None:
        primary = "003B8E"
        thin = Side(style="thin", color="DCE3F0")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.fill = PatternFill("solid", fgColor=primary)
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="top")
        for column_cells in ws.columns:
            letter = get_column_letter(column_cells[0].column)
            max_len = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=0)
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 60)



def main() -> None:
    """Punto de entrada informativo.

    Este modulo contiene solo el motor de procesamiento.
    La interfaz gráfica oficial está en PySide6 y el acceso recomendado
    es main.py.
    """
    print(
        "fase1_recopilacion.py es el motor de procesamiento. "
        "Ejecuta main.py para usar la interfaz gráfica."
    )


if __name__ == "__main__":
    freeze_support()
    main()
