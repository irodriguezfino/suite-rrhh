from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

from core.models import ProcessRequest
from core.exceptions import BatchProcessingError, ProcessingCancelled
from fase1_recopilacion import EMPLOYMENT_MODE_ACTIVE, PROCESS_MODE_DAILY, PROCESS_MODE_MONTHLY, ExcelCollector, department_abbreviation_from_filename, get_monthly_control_month_label, is_hire_date_eligible
from services.fase1_service import Fase1Service
from services.output_lock import OutputLock


class Fase1ServiceTests(unittest.TestCase):
    def test_requires_input_files(self) -> None:
        request = ProcessRequest((), datetime.now(), Path("salida.xlsx"), EMPLOYMENT_MODE_ACTIVE, PROCESS_MODE_DAILY)
        with self.assertRaisesRegex(ValueError, "al menos un archivo"):
            Fase1Service().validate(request)

    def test_rejects_future_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_file = Path(directory) / "entrada.xlsx"
            input_file.touch()
            request = ProcessRequest((input_file,), datetime.now() + timedelta(days=1), Path(directory) / "salida.xlsx", EMPLOYMENT_MODE_ACTIVE, PROCESS_MODE_DAILY)
            with self.assertRaisesRegex(ValueError, "posterior"):
                Fase1Service().validate(request)

    def test_monthly_cycle_selects_closing_month(self) -> None:
        self.assertEqual(get_monthly_control_month_label(datetime(2026, 7, 20).date()), "JULIO")
        self.assertEqual(get_monthly_control_month_label(datetime(2026, 7, 21).date()), "AGOSTO")
        self.assertEqual(get_monthly_control_month_label(datetime(2026, 12, 21).date()), "ENERO")

    def test_matanza_parts_keep_ml_and_ms_abbreviations(self) -> None:
        self.assertEqual(department_abbreviation_from_filename("Parte RT - Matanza Limpia.xlsx"), "ML")
        self.assertEqual(department_abbreviation_from_filename("Toma de datos MS.xlsx"), "MS")
        self.assertEqual(department_abbreviation_from_filename("ParteMensual_Matanza_Zona_Limpia_2026.xlsx"), "ML")
        self.assertEqual(department_abbreviation_from_filename("ParteMensual_Matanza_Zona_Sucia_2026.xlsx"), "MS")
        self.assertEqual(department_abbreviation_from_filename("ParteMensual_RT_2026.xlsx"), "RT")

    def test_hire_date_equal_to_selected_date_is_eligible(self) -> None:
        selected = datetime(2026, 8, 4).date()
        self.assertTrue(is_hire_date_eligible(selected, selected))
        self.assertTrue(is_hire_date_eligible(datetime(2026, 8, 3).date(), selected))
        self.assertFalse(is_hire_date_eligible(datetime(2026, 8, 5).date(), selected))

    def test_accepts_valid_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_file = Path(directory) / "entrada.xlsx"
            input_file.touch()
            request = ProcessRequest((input_file,), datetime.now(), Path(directory) / "salida.xlsx", EMPLOYMENT_MODE_ACTIVE, PROCESS_MODE_MONTHLY)
            Fase1Service().validate(request)

    def test_monthly_preflight_identifies_missing_required_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_file = Path(directory) / "parte_incompleto.xlsx"
            workbook = openpyxl.Workbook()
            workbook.active.title = "Julio"
            workbook.create_sheet("Control 20_20")
            workbook.save(input_file)
            workbook.close()
            request = ProcessRequest(
                (input_file,),
                datetime(2026, 7, 29),
                Path(directory) / "salida.xlsx",
                EMPLOYMENT_MODE_ACTIVE,
                PROCESS_MODE_MONTHLY,
            )
            with self.assertRaisesRegex(BatchProcessingError, "Agosto"):
                Fase1Service().preflight_sources(request)

    def test_cancelled_run_stops_before_opening_excel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            collector = ExcelCollector(
                datetime.now(),
                Path(directory) / "salida.xlsx",
                max_workers=1,
                employment_mode=EMPLOYMENT_MODE_ACTIVE,
                process_mode=PROCESS_MODE_DAILY,
            )
            with self.assertRaises(ProcessingCancelled):
                collector.run([Path(directory) / "no_llega_a_abrirse.xlsx"], should_cancel=lambda: True)

    def test_output_lock_rejects_second_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "salida.xlsx"
            with OutputLock(output):
                with self.assertRaisesRegex(RuntimeError, "Ya hay una recopilación"):
                    with OutputLock(output):
                        pass


if __name__ == "__main__":
    unittest.main()
