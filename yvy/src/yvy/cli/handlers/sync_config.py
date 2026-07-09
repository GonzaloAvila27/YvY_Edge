"""Handler ``configure-sync``: instala credentials + server URL (idempotente)."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from yvy.bootstrap import CoreDependencies

logger = logging.getLogger(__name__)


def _validate_credentials_dict(creds: dict[str, Any]) -> str | None:
    """Valida la estructura de un station_credentials. None si OK."""
    from uuid import UUID

    required = {"station_uuid", "key_version", "key_hmac_hex"}
    missing = required - creds.keys()
    if missing:
        return f"faltan campos: {', '.join(sorted(missing))}"
    try:
        UUID(str(creds["station_uuid"]))
    except ValueError:
        return f"station_uuid no es un UUID válido: {creds['station_uuid']!r}"
    try:
        int(creds["key_version"])
    except (ValueError, TypeError):
        return f"key_version no es entero: {creds['key_version']!r}"
    try:
        key_bytes = bytes.fromhex(str(creds["key_hmac_hex"]))
    except ValueError:
        return "key_hmac_hex no es hexadecimal válido"
    if len(key_bytes) < 32:
        return f"key_hmac_hex muy corto ({len(key_bytes)} bytes, mínimo 32)"
    return None


def configure_sync(
    deps: CoreDependencies,
    *,
    creds_path: Path,
    server_url: str | None,
    force: bool = False,
) -> dict[str, Any]:
    """Setea las credentials de sync del nodo (station_credentials.json + app_config).

    Idempotente: por defecto NO pisa una configuración existente. Se considera
    "ya configurado" cuando existe ``data/station_credentials.json`` Y hay un
    ``sync_server_url`` en app_config. Con ``force=True`` sobrescribe (con backup).

    No re-corre el onboarding ni toca otros datos.

    Returns dict:
        {ok, skipped, reason, station_uuid, server_url, dest_path, error, notes}
    """
    import os

    dest = deps.root / "data" / "station_credentials.json"
    existing_url = deps.app_config_repo.get("sync_server_url")
    already_configured = dest.exists() and bool(existing_url)

    if already_configured and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "already_configured",
            "station_uuid": deps.app_config_repo.get("station_uuid"),
            "server_url": existing_url,
            "dest_path": str(dest),
            "error": None,
            "notes": ["Ya configurado. Usar --force para sobrescribir."],
        }

    url = (server_url or os.environ.get("YVY_SYNC_URL", "")).strip()
    if not url:
        return {
            "ok": False,
            "skipped": False,
            "reason": "no_server_url",
            "station_uuid": None,
            "server_url": None,
            "dest_path": None,
            "error": "Falta la URL del servidor (--server-url o YVY_SYNC_URL).",
            "notes": [],
        }

    if not creds_path.exists():
        return {
            "ok": False,
            "skipped": False,
            "reason": "creds_not_found",
            "station_uuid": None,
            "server_url": None,
            "dest_path": None,
            "error": f"No se encontró el archivo de credentials: {creds_path}",
            "notes": [],
        }

    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "skipped": False,
            "reason": "creds_invalid_json",
            "station_uuid": None,
            "server_url": None,
            "dest_path": None,
            "error": f"el archivo no es JSON válido: {exc}",
            "notes": [],
        }

    err = _validate_credentials_dict(creds)
    if err:
        return {
            "ok": False,
            "skipped": False,
            "reason": "creds_invalid",
            "station_uuid": None,
            "server_url": None,
            "dest_path": None,
            "error": f"credentials inválidas — {err}",
            "notes": [],
        }

    station_uuid = str(creds["station_uuid"])
    notes: list[str] = []

    data_dir = deps.root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        backup = dest.with_suffix(".json.bak")
        try:
            shutil.copy2(dest, backup)
            notes.append(f"Backup del archivo anterior: {backup.name}")
        except PermissionError:
            notes.append("No se pudo backupear (archivo en uso) — se sobrescribe igual")

    shutil.copy2(creds_path, dest)
    deps.app_config_repo.set("sync_server_url", url)
    deps.app_config_repo.set("station_uuid", station_uuid)

    return {
        "ok": True,
        "skipped": False,
        "reason": "configured",
        "station_uuid": station_uuid,
        "server_url": url,
        "dest_path": str(dest),
        "error": None,
        "notes": notes,
    }
