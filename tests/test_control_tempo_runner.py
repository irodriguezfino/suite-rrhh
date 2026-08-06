from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from core.exceptions import ProcessingCancelled
from core.models import ProcessResult, ProgressUpdate
from workers import control_tempo_runner


class ControlTempoRunnerTests(unittest.TestCase):
    def _request_payload(self, directory: Path) -> dict:
        input_file = directory / "parte.xlsx"
        input_file.touch()
        return {
            "input_files": [str(input_file)],
            "selected_date": datetime(2026, 8, 5).isoformat(),
            "output_path": str(directory / "salida.xlsx"),
            "employment_mode": "activos",
            "process_mode": "diario",
        }

    def test_runner_writes_progress_and_result_without_qt(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            request_file = directory / "request.json"
            result_file = directory / "result.json"
            events_file = directory / "events.jsonl"
            cancel_file = directory / "cancel.requested"
            request_file.write_text(json.dumps(self._request_payload(directory)), encoding="utf-8")

            result = ProcessResult(
                output_path=directory / "salida.xlsx",
                worker_count=3,
                elapsed_seconds=1.5,
                detail_lines=("OK",),
                audits=({"status": "OK"},),
            )

            class FakeService:
                def run(self, request, progress_listener, should_cancel):
                    self.request = request
                    progress_listener(ProgressUpdate(event="writing", message="Escribiendo", total_units=2))
                    return result

            with patch.object(control_tempo_runner, "Fase1Service", FakeService):
                self.assertEqual(control_tempo_runner.run(request_file, result_file, events_file, cancel_file), 0)

            payload = json.loads(result_file.read_text(encoding="utf-8"))
            events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["result"]["worker_count"], 3)
            self.assertTrue(any(event["event"] == "progress" for event in events))
            self.assertEqual(events[-1]["event"], "success")

    def test_runner_reports_cancellation_as_a_normal_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            request_file = directory / "request.json"
            result_file = directory / "result.json"
            events_file = directory / "events.jsonl"
            cancel_file = directory / "cancel.requested"
            request_file.write_text(json.dumps(self._request_payload(directory)), encoding="utf-8")

            class FakeService:
                def run(self, *_args, **_kwargs):
                    raise ProcessingCancelled()

            with patch.object(control_tempo_runner, "Fase1Service", FakeService):
                self.assertEqual(control_tempo_runner.run(request_file, result_file, events_file, cancel_file), 0)

            self.assertEqual(json.loads(result_file.read_text(encoding="utf-8"))["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
