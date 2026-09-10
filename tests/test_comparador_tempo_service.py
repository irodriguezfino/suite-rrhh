from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from core.models import ComparatorRequest
from services.comparador_tempo_service import (
    ComparadorTempoService,
    _excel_duration_to_minutes,
    _marking_incidence,
    _to_minutes,
)


class ComparadorTempoServiceTests(unittest.TestCase):
    def test_time_conversion_accepts_excel_and_sap_values(self) -> None:
        self.assertEqual(_to_minutes(0.5), 720)
        self.assertEqual(_to_minutes("16:30"), 990)
        self.assertEqual(_to_minutes("-0:15"), -15)
        self.assertEqual(_to_minutes("�"), 0)

    def test_excel_duration_conversion_keeps_accumulated_hours_over_three_days(self) -> None:
        self.assertEqual(_excel_duration_to_minutes(3 + 70 / 1440), 4390)

    def test_pivot_reader_keeps_accumulated_hours_over_three_days(self) -> None:
        rows = ComparadorTempoService._rows_from_pivot([
            ["Etiquetas de fila", "H. EXTRAS", "HFJ (15%)", "BOLSA (X%)", "NOCTUR", "PENOS", "RUIDO", "ABSENT"],
            ["APARICIO TORRE PABLO", 70 / 1440, 0, 0, 180 / 1440, 0, 3 + 70 / 1440, 0],
        ])

        self.assertEqual(rows[0]["values"]["H. EXTRAS"], 70)
        self.assertEqual(rows[0]["values"]["NOCTUR"], 180)
        self.assertEqual(rows[0]["values"]["RUIDO"], 4390)

    def test_marking_incidence_classification(self) -> None:
        self.assertEqual(_marking_incidence("[55] E 05:23", ""), "Falta fichaje de salida")
        self.assertEqual(_marking_incidence("", ""), "Falta fichaje de entrada")
        self.assertEqual(_marking_incidence("Baja médica", ""), "Baja médica")
        self.assertIsNone(_marking_incidence("Festivo", ""))
        self.assertIsNone(_marking_incidence("[55] E 05:23", "[55] S 13:54"))

    def test_sap_xlsx_is_read_with_the_same_totals_and_marking_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sap_path = Path(directory) / "informe_sap.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Acumulados"
            sheet.append([
                "Fecha", "Trabajador", "1016-HE", "1129-HE15%", "1166-HE30%", "1166-HE35%",
                "1014-HNOC", "1146-PPEN", "1153-PRUI", "1052-HDESC", "Trab. Dia", "Marcajes", "Marcajes",
            ])
            sheet.append(["", "1001 ANA PRUEBA"])
            sheet.append(["", "2026-08-01", None, None, None, None, None, None, None, None, None, "[55] E 05:23", ""])
            sheet.append(["", "1001 ANA PRUEBA"])
            sheet.append(["", "", 0.5, 0, 0, 0, 0, 0, 0, 0, 3 + 70 / 1440])
            workbook.save(sap_path)
            workbook.close()

            totals, duplicates = ComparadorTempoService._read_sap_totals(sap_path)

            self.assertEqual(duplicates, set())
            self.assertEqual(totals["1001"]["worker"], "ANA PRUEBA")
            self.assertEqual(totals["1001"]["values"]["1016-HE"], 720)
            self.assertEqual(totals["1001"]["values"]["1129-HE15%"], 0)
            self.assertEqual(totals["1001"]["values"]["Trab. Dia"], 4390)
            self.assertEqual(totals["1001"]["values"]["1153-PRUI"], 0)
            self.assertEqual(totals["1001"]["values"]["1052-HDESC"], 0)
            self.assertEqual(totals["1001"]["marking_incidents"], ("Falta fichaje de salida",))

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
                    "1001": {"worker": "ANA SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1002": {"worker": "BEA SAP", "values": {"1016-HE": 120, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1003": {"worker": "CARLOS SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
                    "1004": {"worker": "SOLO SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}},
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
            self.assertEqual(workbook["Resultado"][6][6].value, "-1:00")
            self.assertTrue(workbook["Resultado"][6][6].fill.fgColor.rgb.endswith("FFF4CC"))
            workbook.close()
            incidents_workbook = load_workbook(result.incidents_path, data_only=True)
            headers = [cell.value for cell in incidents_workbook["Incidencias"][1]]
            self.assertIn("Trabajador Partes mensuales", headers)
            self.assertIn("Partes mensuales · H. EXTRAS", headers)
            self.assertIn("Valor Partes mensuales", headers)
            self.assertIn("Tempo · 1016-HE", headers)
            self.assertIn("Valor Tempo", headers)
            self.assertNotIn("Valor SAP", headers)
            incidents_workbook.close()

    def test_normal_sections_compare_extra_hours_and_hfj_with_their_sap_fields(self) -> None:
        """1016-HE corresponde a extras y 1129-HE15% a HFJ (15%) en secciones normales."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            values = {"H. EXTRAS": 30, "HFJ (15%)": 500, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}
            sap_values = {
                "1016-HE": 30,
                "1129-HE15%": 500,
                "1166-HE30%": 0,
                "1166-HE35%": 0,
                "1014-HNOC": 0,
                "1146-PPEN": 0,
                "1153-PRUI": 0,
                "1052-HDESC": 0,
                "Trab. Dia": 0,
            }

            result = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"SK": [{"worker": "Carmen", "values": values}]},
                lambda _path: ({"SK": {"CARMEN": {"106930"}}}, []),
                lambda _path: ({"106930": {"worker": "CARMEN", "values": sap_values}}, set()),
            ).run(ComparatorRequest(tempo, sap, output))

            self.assertEqual(result.rows, ())
            self.assertFalse(any(item.field == "H. EXTRAS" for item in result.incidents))

    def test_control_difference_includes_worker_and_is_highlighted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            values = {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 450, "ABSENT": 0}
            sap_values = {
                "1016-HE": 0, "1129-HE15%": 0, "1166-HE30%": 0, "1166-HE35%": 0,
                "1014-HNOC": 0, "1146-PPEN": 0, "1153-PRUI": 0, "1052-HDESC": 0,
                "Trab. Dia": 480,
            }

            result = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"MTO": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"MTO": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA", "values": sap_values}}, set()),
            ).run(ComparatorRequest(tempo, sap, output))

            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0].trigger_fields, ("Control",))
            self.assertEqual(result.rows[0].sap_daily_minus_noise_minutes, 30)
            self.assertTrue(any(item.field == "Control" for item in result.incidents))
            workbook = load_workbook(output)
            sheet = workbook["Resultado"]
            self.assertEqual(sheet.cell(5, 4).value, "Control")
            self.assertEqual(sheet.cell(6, 4).value, "+0:30")
            self.assertTrue(sheet.cell(6, 4).fill.fgColor.rgb.endswith("FFF4CC"))
            workbook.close()

    def test_special_sap_controls_and_absence_are_included_in_red(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tempo, sap, output = root / "tempo.xlsx", root / "sap.xls", root / "resultado.xlsx"
            tempo.touch()
            sap.touch()
            zero = {"H. EXTRAS": 0, "HFJ (15%)": 0, "BOLSA (X%)": 0, "NOCTUR": 0, "PENOS": 0, "RUIDO": 0, "ABSENT": 0}
            absent = {**zero, "ABSENT": 60}

            def sap_values(**overrides):
                return {
                    "1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0,
                    "1014-HNOC": 0, "1146-PPEN": 0, "1153-PRUI": 0,
                    "1052-HDESC": 0, "Trab. Dia": 0, **overrides,
                }

            result = ComparadorTempoService(
                lambda _path, _cancel, _progress: {
                    "MTO": [{"worker": "Marta", "values": zero}],
                    "ADMON": [{"worker": "Ana", "values": zero}],
                    "TR": [{"worker": "Pepa", "values": zero}],
                    "L3": [{"worker": "Berta", "values": absent}],
                },
                lambda _path: ({
                    "MTO": {"MARTA": {"1001"}}, "ADMON": {"ANA": {"1002"}},
                    "TR": {"PEPA": {"1003"}}, "L3": {"BERTA": {"1004"}},
                }, []),
                lambda _path: ({
                    "1001": {"worker": "MARTA", "values": sap_values(**{"1153-PRUI": 30})},
                    "1002": {"worker": "ANA", "values": sap_values(**{"1014-HNOC": 45})},
                    "1003": {"worker": "PEPA", "values": sap_values(**{"1146-PPEN": 15})},
                    "1004": {"worker": "BERTA", "values": sap_values(**{"1052-HDESC": 60})},
                }, set()),
            ).run(ComparatorRequest(tempo, sap, output))

            by_worker = {row.worker: row for row in result.rows}
            self.assertEqual(set(by_worker), {"Marta", "Ana", "Pepa", "Berta"})
            self.assertEqual(by_worker["Marta"].values_minutes["RUIDO"], 30)
            self.assertEqual(by_worker["Marta"].red_fields, ("RUIDO",))
            self.assertEqual(by_worker["Ana"].values_minutes["NOCTUR"], 45)
            self.assertIn("NOCTUR", by_worker["Ana"].red_fields)
            self.assertEqual(by_worker["Pepa"].values_minutes["PENOS"], 15)
            self.assertIn("PENOS", by_worker["Pepa"].red_fields)
            self.assertEqual(by_worker["Berta"].values_minutes["ABSENT"], 0)
            self.assertEqual(by_worker["Berta"].red_fields, ("ABSENT",))
            self.assertTrue(any(item.incident_type == "Control especial Tempo" for item in result.incidents))
            self.assertTrue(any(item.incident_type == "Absentismo" for item in result.incidents))

            workbook = load_workbook(output)
            sheet = workbook["Resultado"]
            worker_rows = {
                str(sheet.cell(row_number, 1).value): row_number
                for row_number in range(1, sheet.max_row + 1)
                if sheet.cell(row_number, 1).value in {"Marta", "Berta"}
            }
            marta_header = worker_rows["Marta"] - 1
            berta_header = worker_rows["Berta"] - 1
            marta_columns = {
                str(sheet.cell(marta_header, column).value): column
                for column in range(1, sheet.max_column + 1)
            }
            berta_columns = {
                str(sheet.cell(berta_header, column).value): column
                for column in range(1, sheet.max_column + 1)
            }
            ruido_cell = sheet.cell(worker_rows["Marta"], marta_columns["Δ RUIDO"])
            absent_cell = sheet.cell(worker_rows["Berta"], berta_columns["ABSENT"])
            self.assertEqual(ruido_cell.value, "0:30")
            self.assertEqual(absent_cell.value, "0:00")
            self.assertTrue(ruido_cell.fill.fgColor.rgb.endswith("FDE2E1"))
            self.assertTrue(absent_cell.fill.fgColor.rgb.endswith("FDE2E1"))
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
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 480}, "marking_incidents": ("Falta fichaje de salida",)}}, set()),
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
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 0, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}, "marking_incidents": ("VACACIONES",)}}, set()),
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
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1016-HE": 999, "1166-HE30%": 0, "1166-HE35%": 180, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}}}, set()),
            )
            no_difference = service.run(ComparatorRequest(tempo, sap, output))
            self.assertEqual(no_difference.rows, ())

            with_difference = ComparadorTempoService(
                lambda _path, _cancel, _progress: {"ML": [{"worker": "Ana", "values": values}]},
                lambda _path: ({"ML": {"ANA": {"1001"}}}, []),
                lambda _path: ({"1001": {"worker": "ANA SAP", "values": {"1016-HE": 0, "1166-HE30%": 0, "1166-HE35%": 240, "1014-HNOC": 0, "1146-PPEN": 0, "Trab. Dia": 0}}}, set()),
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
