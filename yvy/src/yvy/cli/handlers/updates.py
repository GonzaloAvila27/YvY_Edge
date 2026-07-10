"""Handlers del subsistema de actualizaciones.

Toda la infraestructura la provee ``deps.updates_service`` (INI-3 · 3.2.3);
acá no se construye nada."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from yvy.bootstrap import CoreDependencies

logger = logging.getLogger(__name__)


def download_update(
    deps: CoreDependencies,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Descarga el paquete de update pendiente y verifica su integridad.

    Retorna dict con:
        ok: bool
        already_downloaded: bool
        version: str | None
        bytes_downloaded: int
        error: str | None
        dest_path: str | None
    """
    # Nodo sin sync configurado: se reporta antes que nada (orden histórico).
    creds_path = deps.root / "data" / "station_credentials.json"
    if not deps.app_config_repo.get("sync_server_url") or not creds_path.exists():
        return {
            "ok": False,
            "already_downloaded": False,
            "version": None,
            "bytes_downloaded": 0,
            "error": "sync_no_config: sin credentials o server_url no configurado",
            "dest_path": None,
        }

    # Sin update pendiente: nada que hacer (no es un error).
    pending = deps.app_config_repo.get_pending_update()
    if pending is None:
        return {
            "ok": True,
            "already_downloaded": False,
            "version": None,
            "bytes_downloaded": 0,
            "error": None,
            "dest_path": None,
        }

    # El UpdatesService resuelve credenciales/HttpClient y garantiza el cierre.
    # Acá no se construye infraestructura (INI-3 · 3.2.3).
    out = deps.updates_service.download(progress_callback=progress_callback)
    return {
        "ok": out["ok"],
        "already_downloaded": out["already_downloaded"],
        "version": pending.get("edge_version"),
        "bytes_downloaded": out["bytes_downloaded"],
        "error": out["error"],
        "dest_path": out["dest_path"],
    }


def compute_check_updates(deps: CoreDependencies) -> dict[str, Any]:
    """Consulta GET /api/v1/edge/sync y retorna el estado de actualizaciones.

    Retorna dict con:
        ok: bool
        current_version: str
        last_sync_version: int
        server_sync_version: int | None
        update_available: bool
        pending: dict | None
        error: str | None
    """
    import json as _json
    from uuid import UUID

    from yvy import __version__

    creds_path = deps.root / "data" / "station_credentials.json"

    server_url = deps.app_config_repo.get("sync_server_url")
    if not server_url:
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": deps.app_config_repo.get_last_sync_version(),
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": "sync_server_url no configurado — ejecutar onboarding primero",
        }

    if not creds_path.exists():
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": deps.app_config_repo.get_last_sync_version(),
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": f"credentials no encontradas en {creds_path}",
        }

    try:
        creds = _json.loads(creds_path.read_text(encoding="utf-8-sig"))
        station_uuid = UUID(creds["station_uuid"])
        key_version = int(creds["key_version"])
        key_bytes = bytes.fromhex(creds["key_hmac_hex"])
    except Exception as exc:
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": deps.app_config_repo.get_last_sync_version(),
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": f"credentials inválidas: {exc}",
        }

    from yvy.infrastructure.sync.http_client import (
        AuthError,
        HttpClient,
        MalformedResponseError,
        NetworkError,
        SendError,
        StationNotFoundError,
    )

    http_client = HttpClient(server_url=server_url, verify=True)
    last_sv = deps.app_config_repo.get_last_sync_version()

    try:
        response = http_client.get_edge_sync(
            station_uuid=station_uuid,
            key_version=key_version,
            last_sync_version=last_sv,
            edge_version=__version__,
            key=key_bytes,
            timeout_s=10.0,
        )
    except AuthError as exc:
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": last_sv,
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": f"auth error: {exc}",
        }
    except StationNotFoundError as exc:
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": last_sv,
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": f"station_uuid desconocido: {exc}",
        }
    except (NetworkError, MalformedResponseError, SendError) as exc:
        return {
            "ok": False,
            "current_version": __version__,
            "last_sync_version": last_sv,
            "server_sync_version": None,
            "update_available": False,
            "pending": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        try:
            http_client.close()
        except Exception as exc:
            logger.debug("Error cerrando http_client (ignorado): %s", exc)

    # Persistir resultado
    deps.app_config_repo.set_last_sync_version(response.sync_version)
    if response.update_available and response.update_metadata:
        deps.app_config_repo.set_pending_update(response.update_metadata)
    else:
        # ERR-003: sin update disponible → limpiar pending obsoleto (release
        # despublicado en el server). Si no, el nodo lo seguiría ofreciendo.
        deps.app_config_repo.clear_pending_update()

    return {
        "ok": True,
        "current_version": __version__,
        "last_sync_version": last_sv,
        "server_sync_version": response.sync_version,
        "update_available": response.update_available,
        "pending": response.update_metadata,
        "error": None,
    }


def compute_update_status(deps: CoreDependencies) -> dict[str, Any]:
    """Estado del sistema de updates: versión, slots, releases, pending."""
    from yvy import __version__

    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "name": "Versión instalada",
            "status": "info",
            "detail": __version__,
            "value": __version__,
        }
    )

    current = deps.app_config_repo.get_current_release()
    previous = deps.app_config_repo.get_previous_release()
    stable = deps.app_config_repo.get_last_stable_release()

    if current:
        checks.append(
            {
                "name": "Release actual (current)",
                "status": "info",
                "detail": current,
                "value": current,
            }
        )
        if previous:
            checks.append(
                {
                    "name": "Release anterior (previous)",
                    "status": "info",
                    "detail": previous,
                    "value": previous,
                }
            )
        if stable:
            checks.append(
                {
                    "name": "Último estable (last_stable)",
                    "status": "info",
                    "detail": stable,
                    "value": stable,
                }
            )
    else:
        checks.append(
            {
                "name": "Modo de instalación",
                "status": "warn",
                "detail": "flat (sin slots — primera actualización migrará automáticamente)",
                "value": "flat",
            }
        )

    releases = deps.updates_service.get_releases_on_disk()
    if releases:
        details = "  ·  ".join(
            f"{r['version']}" + (f" ({', '.join(r['states'])})" if r["states"] else "")
            for r in releases
        )
        checks.append(
            {
                "name": "Releases en disco",
                "status": "info",
                "detail": details,
                "value": [{"version": r["version"], "states": r["states"]} for r in releases],
            }
        )

    pending = deps.app_config_repo.get_pending_update()
    if pending:
        to_ver = pending.get("edge_version", "?")
        is_dl = deps.app_config_repo.is_update_downloaded()
        dl_label = "descargado ✓" if is_dl else "pendiente de descarga"
        size_mb = pending.get("package_size_bytes", 0) / (1024 * 1024)
        checks.append(
            {
                "name": "Actualización disponible",
                "status": "ok" if is_dl else "warn",
                "detail": f"v{to_ver}  {size_mb:.1f} MB  ({dl_label})",
                "value": {"version": to_ver, "is_downloaded": is_dl},
            }
        )
    else:
        checks.append(
            {
                "name": "Actualización disponible",
                "status": "ok",
                "detail": "al día — no hay updates pendientes",
                "value": None,
            }
        )

    install_status = deps.app_config_repo.get_install_status()
    if install_status and install_status not in ("completed", "failed"):
        to_v = deps.app_config_repo.get_install_to_version() or "?"
        checks.append(
            {
                "name": "Instalación en curso",
                "status": "warn",
                "detail": f"estado={install_status}  destino={to_v}",
                "value": {"status": install_status, "to_version": to_v},
            }
        )

    return {
        "ok": True,
        "checks": checks,
        "notes": [],
        "summary": f"YVY Edge v{__version__}",
    }


def execute_update_install(deps: CoreDependencies) -> dict[str, Any]:
    """Lanza INSTALL_UPDATE.bat tras prevalidar y escribir params.

    En el contexto CLI no hay usuario autenticado; se registra user_id=None
    (evento SYSTEM).

    Retorna dict con:
        ok: bool
        prevalidation_ok: bool
        reason: str | None   (si prevalidation falla)
        launched: bool
        error: str | None
    """
    pre = deps.updates_service.prevalidate()
    if pre is None or not pre.ok:
        return {
            "ok": False,
            "prevalidation_ok": False,
            "reason": pre.reason if pre is not None else "prevalidación falló",
            "launched": False,
            "error": None,
        }

    request = deps.updates_service.request_install(None)
    if not request.ok:
        return {
            "ok": False,
            "prevalidation_ok": True,
            "reason": None,
            "launched": False,
            "error": request.error,
        }

    return {
        "ok": True,
        "prevalidation_ok": True,
        "reason": None,
        "launched": True,
        "error": None,
    }


def execute_rollback(
    deps: CoreDependencies,
    *,
    to_version: str,
    reason: str,
) -> dict[str, Any]:
    """Rollback manual a un release en disco.

    Retorna dict con:
        ok: bool
        to_version: str
        reason: str | None
    """
    result = deps.updates_service.rollback(
        to_version=to_version,
        reason=reason,
        user_id=None,
    )
    if result is None:
        return {"ok": False, "to_version": to_version, "reason": "error interno en rollback"}
    return {
        "ok": result.ok,
        "to_version": result.to_version,
        "reason": result.reason,
    }


def execute_mark_stable(
    deps: CoreDependencies,
    *,
    version: str,
) -> dict[str, Any]:
    """Marca una versión como last_stable manualmente.

    Retorna dict con:
        ok: bool
        version: str
        error: str | None
    """
    result = deps.updates_service.mark_stable(version, None)
    if not result.ok:
        return {"ok": False, "version": version, "error": result.error}

    return {"ok": True, "version": version, "error": None}
