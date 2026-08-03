"""Configuracion local no versionada de la aplicacion."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.app_info import APP_NAME


def get_install_directory() -> Path:
    """Directorio por usuario usado por el instalador universal."""
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return local_app_data / "Programs" / APP_NAME


def get_config_path() -> Path:
    override = os.environ.get("SUITE_RRHH_CONFIG_PATH", "").strip()
    return Path(override).expanduser() if override else get_install_directory() / "config.json"


def get_excel_password() -> str:
    """Obtiene la contraseña local de los libros sin incluirla en el código."""
    environment_password = os.environ.get("SUITE_RRHH_EXCEL_PASSWORD", "")
    if environment_password:
        return environment_password

    config_path = get_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "No se encontró la configuración local de Suite RRHH. "
            f"Debe existir el archivo: {config_path}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer la configuración local: {config_path}") from exc

    password = str(payload.get("excel_password", ""))
    if not password:
        raise RuntimeError(f"Falta 'excel_password' en la configuración local: {config_path}")
    return password
