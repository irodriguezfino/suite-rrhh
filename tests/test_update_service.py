from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.config import get_excel_password
from services.update_service import UpdateInfo, UpdateService, _version_key


class UpdateServiceTests(unittest.TestCase):
    def test_version_comparison_key(self) -> None:
        self.assertGreater(_version_key("1.10.0"), _version_key("1.2.9"))
        self.assertEqual(_version_key("v1.0.0"), (1, 0, 0))

    def test_manifest_accepts_official_package(self) -> None:
        UpdateService._validate_manifest(UpdateInfo(
            version="1.0.1",
            package_url="https://raw.githubusercontent.com/irodriguezfino/suite-rrhh/main/updates/Suite_RRHH_update_1.0.1.zip",
            sha256="a" * 64,
        ))

    def test_manifest_rejects_untrusted_package(self) -> None:
        with self.assertRaises(ValueError):
            UpdateService._validate_manifest(UpdateInfo(
                version="1.0.1",
                package_url="https://example.com/update.zip",
                sha256="a" * 64,
            ))

    def test_excel_password_reads_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text('{"excel_password": "test-password"}', encoding="utf-8")
            previous_path = os.environ.get("SUITE_RRHH_CONFIG_PATH")
            previous_password = os.environ.pop("SUITE_RRHH_EXCEL_PASSWORD", None)
            os.environ["SUITE_RRHH_CONFIG_PATH"] = str(config)
            try:
                self.assertEqual(get_excel_password(), "test-password")
            finally:
                if previous_path is None:
                    os.environ.pop("SUITE_RRHH_CONFIG_PATH", None)
                else:
                    os.environ["SUITE_RRHH_CONFIG_PATH"] = previous_path
                if previous_password is not None:
                    os.environ["SUITE_RRHH_EXCEL_PASSWORD"] = previous_password


if __name__ == "__main__":
    unittest.main()
