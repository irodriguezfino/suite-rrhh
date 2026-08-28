"""Comprobacion y lanzamiento seguro de actualizaciones publicadas en GitHub."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.app_info import APP_VERSION, REPOSITORY_OWNER, REPOSITORY_NAME, UPDATE_MANIFEST_URL
from core.config import get_install_directory


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    package_url: str
    sha256: str


def _version_key(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", value.strip())
    if not match:
        raise ValueError(f"Versión no válida en el manifiesto: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


class UpdateService:
    """Lee exclusivamente el canal oficial público de actualización."""

    def check_for_update(self, timeout_seconds: int = 4) -> UpdateInfo | None:
        request = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "Suite-RRHH-Updater"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))

        info = UpdateInfo(
            version=str(payload["version"]),
            package_url=str(payload["package_url"]),
            sha256=str(payload["sha256"]).lower(),
        )
        self._validate_manifest(info)
        return info if _version_key(info.version) > _version_key(APP_VERSION) else None

    @staticmethod
    def _validate_manifest(info: UpdateInfo) -> None:
        package = urllib.parse.urlparse(info.package_url)
        allowed_host = "raw.githubusercontent.com"
        expected_path = f"/{REPOSITORY_OWNER}/{REPOSITORY_NAME}/main/updates/"
        if package.scheme != "https" or package.hostname != allowed_host or not package.path.startswith(expected_path):
            raise ValueError("El paquete de actualización no pertenece al canal oficial de Suite RRHH.")
        if not re.fullmatch(r"[0-9a-f]{64}", info.sha256):
            raise ValueError("El manifiesto de actualización no contiene un SHA-256 válido.")

    @staticmethod
    def launch_updater() -> None:
        install_dir = get_install_directory()
        runtime = install_dir / "runtime"
        updater = install_dir / "app" / "updater.py"
        python = runtime / "pythonw.exe"
        if not python.exists():
            python = runtime / "python.exe"
        if not updater.exists() or not python.exists():
            raise RuntimeError("No se encontró el actualizador de la instalación actual.")
        subprocess.Popen(
            [str(python), str(updater), "--install-dir", str(install_dir), "--manifest-url", UPDATE_MANIFEST_URL],
            cwd=str(install_dir),
            close_fds=True,
        )

    @staticmethod
    def is_installed_copy() -> bool:
        """Evita actualizar una ejecución local que reutiliza el runtime instalado.

        Para probar código fuente local se puede usar el ``python.exe`` de la
        instalación. Mirar solo el ejecutable confundía esa situación con una
        copia instalada e iniciaba el actualizador en segundo plano.
        """
        runtime = (get_install_directory() / "runtime").resolve()
        installed_app = (get_install_directory() / "app").resolve()
        source_root = Path(__file__).resolve().parents[1]
        return Path(sys.executable).resolve().parent == runtime and source_root == installed_app
