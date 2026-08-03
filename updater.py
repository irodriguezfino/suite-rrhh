"""Actualizador independiente: descarga, valida, instala y reinicia Suite RRHH."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from core.app_info import REPOSITORY_NAME, REPOSITORY_OWNER


def _message(text: str, title: str = "Suite RRHH - Actualización") -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        pass


def _download_manifest(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Suite-RRHH-Updater"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _download_package(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Suite-RRHH-Updater"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise RuntimeError("La comprobación de integridad SHA-256 de la actualización ha fallado.")


def _validate_manifest(manifest: dict) -> tuple[str, str]:
    """Acepta exclusivamente paquetes servidos por el repositorio oficial."""
    package_url = str(manifest["package_url"])
    sha256 = str(manifest["sha256"]).lower()
    package = urllib.parse.urlparse(package_url)
    expected_path = f"/{REPOSITORY_OWNER}/{REPOSITORY_NAME}/main/updates/"
    if (
        package.scheme != "https"
        or package.hostname != "raw.githubusercontent.com"
        or not package.path.startswith(expected_path)
    ):
        raise RuntimeError("El paquete no pertenece al canal oficial de actualizaciones.")
    if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
        raise RuntimeError("El manifiesto no contiene una suma SHA-256 valida.")
    return package_url, sha256


def _terminate_suite_processes(install_dir: Path) -> None:
    """Cierra solo procesos Python de esta instalación y nunca el actualizador actual."""
    try:
        import win32com.client
        query = "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe'"
        processes = win32com.client.GetObject("winmgmts:").ExecQuery(query)
    except Exception:
        return

    target = str(install_dir).casefold()
    current_pid = os.getpid()
    for process in processes:
        pid = int(process.ProcessId)
        command = str(process.CommandLine or "").casefold()
        if pid != current_pid and target in command:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as package:
        root = destination.resolve()
        for item in package.infolist():
            candidate = (destination / item.filename).resolve()
            if candidate != root and root not in candidate.parents:
                raise RuntimeError("El paquete contiene una ruta no válida.")
        package.extractall(destination)


def _install_app(staging: Path, install_dir: Path) -> None:
    staged_app = staging / "app"
    if not staged_app.is_dir():
        raise RuntimeError("El paquete de actualización no contiene la carpeta app esperada.")

    app_dir = install_dir / "app"
    backup_dir = install_dir / "app.backup"
    shutil.rmtree(backup_dir, ignore_errors=True)
    if app_dir.exists():
        app_dir.replace(backup_dir)
    try:
        staged_app.replace(app_dir)
    except Exception:
        if backup_dir.exists() and not app_dir.exists():
            backup_dir.replace(app_dir)
        raise
    shutil.rmtree(backup_dir, ignore_errors=True)


def _restart(install_dir: Path) -> None:
    pythonw = install_dir / "runtime" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = install_dir / "runtime" / "python.exe"
    subprocess.Popen([str(pythonw), str(install_dir / "app" / "main.py")], cwd=str(install_dir / "app"), close_fds=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--manifest-url", required=True)
    arguments = parser.parse_args()
    install_dir = Path(arguments.install_dir).resolve()

    try:
        # Da tiempo a que la interfaz confirme la actualización y cierre su evento.
        time.sleep(1)
        _terminate_suite_processes(install_dir)
        with tempfile.TemporaryDirectory(prefix="Suite_RRHH_Update_") as temp_directory:
            temp = Path(temp_directory)
            manifest = _download_manifest(arguments.manifest_url)
            package_url, sha256 = _validate_manifest(manifest)
            archive = temp / "update.zip"
            _download_package(package_url, archive)
            _verify_sha256(archive, sha256)
            staging = temp / "staging"
            staging.mkdir()
            _safe_extract(archive, staging)
            _install_app(staging, install_dir)
        _restart(install_dir)
        return 0
    except Exception as exc:
        _message(f"No se pudo instalar la actualización.\n\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
