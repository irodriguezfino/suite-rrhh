from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from core.models import ComparatorRequest
from services.comparador_tempo_service import ComparadorTempoService, _marking_incidence, _to_minutes


class ComparadorTempoServiceTests(unittest.TestCase):
    def test_time_conversion_accepts_excel_and_sap_values(self) -> None:
        self.assertEqual(_to_minutes(0.5), 720)
        self.assertEqual(_to_minutes("16:30"), 990)
        self.assertEqual(_to_minutes("-0:15"), -15)
        self.assertEqual(_to_minutes("�"), 0)

    def test_marking_incidence_classification(self) -> None:
        self.assertEqual(_marking_incidence("[55] E 05:23", ""), "Falta fichaje de salida")
        self.assertEqual(_marking_incidence("", ""), "Falta fichaje de entrada")
        self.assertEqual(_marking_incidence("Baja médica", ""), "Baja médica")
        self.assertIsNone(_marking_incidence("Festivo", ""))
        self.assertIsNone(_marking_incidence("[55] E 05:23", "[55] S 13:54"))

    def test_comparison_exports_only_relevant_workers_and_incidents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()

            def identities(_path):
                return {"TR": {"ANA": {"1001"}, "BEA": {"1002"}, "CARLOS": {"1003"}}}, []

            def tempo_reader(_path, _cancel, _progress):
                return {"TR": [
                    {"worker": "Ana", "values": {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 60, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}},
                    {"worker": "Bea", "values": {"H. EXTRAS": 120, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}},
                    {"worker": "Carlos", "values": {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}},
                ]}

            def sap_reader(_path):
                return {
                    "1001": {"worker": "ANA SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1002": {"worker": "BEA SAP", "values": {"1129-HE15%": 120, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1003": {"worker": "CARLOS SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1004": {"worker": "SOLO SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                }, set()

            result = ComparadorTempoService(tempo_reader, identities, sap_reader).run(ComparatorRequest(tempo, sap, output))
            self.assertEqual([row.worker for row in result.rows], ["Ana"])
            self.assertEqual(result.rows[0].trigger_fields, ("BOLSA (X%)",))
            self.assertEqual(result.rows[0].values_minutes["BOLSA (X%)"], -60)
            self.assertEqual(result.rows[0].sap_daily_work_minutes, 0)
            self.assertEqual(len(result.incidents), 2)
            self.assertTrue(output.exists())
            self.assertTrue(result.incidents_path.exists())
            workbook = load_workbook(output, data_only=True)
            self.assertEqual(workbook["Resultado"][1][0].value, "Comparador de Tempo · Resultado")
            self.assertEqual(workbook["Resultado"][6][5].value, "-1:00")
            self.assertTrue(workbook["Resultado"][6][5].fill.fgColor.rgb.endswith("FFF4CC"))
            workbook.close()

    def test_marking_incidence_includes_worker_without_time_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            values = {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}

            result = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"TR": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"TR": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 480}, "marking_incidents": ("Falta fichaje de salida",)}}, set()),
            ).run(ComparatorRequest(tempo, sap, output))

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0].incidence_messages, ("Falta fichaje de salida",))
            self.assertEqual(result.rows[0].sap_daily_work_minutes, 480)
            self.assertEqual(result.rows[0].values_minutes["H. EXTRAS"], 0)
            self.assertTrue(any(item.incident_type == "Incidencia de marcaje" for item in result.incidents))

    def test_named_marking_incidence_without_difference_is_audited_but_not_exported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            values = {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}

            result = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"TR": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"TR": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}, "marking_incidents": ("VACACIONES",)}}, set()),
            ).run(ComparatorRequest(tempo, sap, output))

            self.assertEqual(result.rows, ())
            self.assertTrue(any(item.reason == "VACACIONES" for item in result.incidents))

    def test_ml_compares_combined_extra_and_bolsa_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            values = {"H. EXTRAS": 120, "HFJ (15%)": 0, "BOLSA (X%)": 60, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}

            service = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"ML": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"ML": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1129-HE15%": 999, "1166-HE30%": 0, "1166-HE35%": 180, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}}}, set()),
            )
            no_difference = service.run(ComparatorRequest(tempo, sap, output))
            self.assertEqual(no_difference.rows, ())

            with_difference = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"ML": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"ML": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 240, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}}}, set()),
            ).run(ComparatorRequest(tempo, sap, root / "resultado_con_diferencia.xlsx"))

            self.assertEqual(len(with_difference.rows), 1)
            row = with_difference.rows[0]
            self.assertEqual(row.values_minutes["BOLSA (X%)"], 60)
            self.assertEqual(row.trigger_fields, ("BOLSA (X%)",))
            self.assertEqual(row.suppressed_fields, ("H. EXTRAS",))

    def test_atomic_save_recovers_when_the_requested_output_is_locked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            requested = Path(directory) / "resultado.xlsx"
            workbook = Workbook()
            workbook.active["A1"] = "Resultado recuperable"
            original_replace = __import__("services.comparador_tempo_service", fromlist=["os"]).os.replace

            def replace_with_locked_target(source, destination):
                if Path(destination) == requested:
                    error = PermissionError(5, "Acceso denegado", str(requested))
                    error.winerror = 5
                    raise error
                return original_replace(source, destination)

            with patch("services.comparador_tempo_service.OUTPUT_REPLACE_ATTEMPTS", 1), patch("services.comparador_tempo_service.os.replace", side_effect=replace_with_locked_target):
                saved = ComparadorTempoService._atomic_save(workbook, requested)

            self.assertNotEqual(saved, requested)
            self.assertTrue(saved.is_file())
            self.assertIn("_recuperado_", saved.stem)


if __name__ == "__main__":
    unittest.main()
