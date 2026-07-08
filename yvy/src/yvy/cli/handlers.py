"""Handlers de comandos CLI: funciones puras.

Cada handler:
    1. Recibe ``CoreDependencies`` + parámetros específicos.
    2. Computa un report (dict serializable).
    3. NO imprime nada. NO conoce el formato de salida.

Esto permite que en Ola 2 los mismos handlers se envuelvan en un
decorador ``@command("name")`` y devuelvan el report como JSON para
ejecución remota desde Core. Cero refactor de la lógica.

Convención del report:
    {
        "ok": bool,           # ¿salió todo OK?
        "checks": [
            {
                "name": str,
                "status": "ok" | "fail" | "warn" | "info",
                "detail": str | None,
                "value": Any | None,  # valor crudo para programmatic use
            },
            ...
        ],
        "notes": [str, ...],  # mensajes adicionales al final
        "summary": str,       # resumen one-line
    }
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from yvy.bootstrap import CoreDependencies
from yvy.domain.sync.enums import SyncStatus

logger = logging.getLogger(__name__)


# ─── update download ─────────────────────────────────────────────────────


def download_update(
    deps: CoreDependencies,
    progress_callback=None,  # type: ignore[no-untyped-def]
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
    import json as _json
    from uuid import UUID

    creds_path = deps.root / "data" / "station_credentials.json"
    server_url = deps.app_config_repo.get("sync_server_url")

    if not server_url or not creds_path.exists():
        return {
            "ok": False,
            "already_downloaded": False,
            "version": None,
            "bytes_downloaded": 0,
            "error": "sync_no_config: sin credentials o server_url no configurado",
            "dest_path": None,
        }

    # Verificar que hay un update pendiente
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

    try:
        creds = _json.loads(creds_path.read_text(encoding="utf-8-sig"))
        station_uuid = UUID(creds["station_uuid"])
        key_version = int(creds["key_version"])
        key_bytes = bytes.fromhex(creds["key_hmac_hex"])
    except Exception as exc:
        return {
            "ok": False,
            "already_downloaded": False,
            "version": pending.get("edge_version"),
            "bytes_downloaded": 0,
            "error": f"credentials_invalid: {exc}",
            "dest_path": None,
        }

    from yvy.infrastructure.sync.http_client import HttpClient
    from yvy.infrastructure.sync.update_downloader import UpdateDownloader

    updates_dir = deps.root / "data" / "updates"
    http_client = HttpClient(server_url=server_url, verify=True)
    downloader = UpdateDownloader(
        http_client=http_client,
        app_config_repo=deps.app_config_repo,
        station_uuid=station_uuid,
        key_version=key_version,
        key=key_bytes,
        updates_dir=updates_dir,
    )

    try:
        # Ya descargado y verificado
        if downloader.is_already_downloaded():
            return {
                "ok": True,
                "already_downloaded": True,
                "version": pending.get("edge_version"),
                "bytes_downloaded": 0,
                "error": None,
                "dest_path": deps.app_config_repo.get("update_pending.local_path"),
            }

        result = downloader.download(progress_callback=progress_callback)
    finally:
        try:
            http_client.close()
        except Exception as exc:
            logger.debug("Error cerrando http_client (ignorado): %s", exc)

    return {
        "ok": result.success,
        "already_downloaded": False,
        "version": pending.get("edge_version"),
        "bytes_downloaded": result.bytes_downloaded,
        "error": result.error,
        "dest_path": str(result.dest_path) if result.success else None,
    }


# ─── status: panorama general ────────────────────────────────────────────


def compute_status(deps: CoreDependencies) -> dict[str, Any]:
    """Computa snapshot rápido del estado del nodo.

    Comprobaciones:
      - DB: existe + abre + tamaño.
      - Sensor: último reading registrado, hace cuánto.
      - Sync agent: si hay credentials configuradas.
      - Cola sync: counts por status.

    NO consulta hardware (sensor USB) ni hace red. Para eso están
    los ``test`` específicos.
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. DB
    try:
        db_size = deps.db_path.stat().st_size if deps.db_path.exists() else 0
        from yvy.cli.formatting import fmt_bytes
        checks.append({
            "name": "Base de datos",
            "status": "ok",
            "detail": f"{deps.db_path.name} ({fmt_bytes(db_size)})",
            "value": {"path": str(deps.db_path), "size_bytes": db_size},
        })
    except Exception as exc:
        overall_ok = False
        checks.append({
            "name": "Base de datos",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    # 2. Último sensor reading
    try:
        # Buscamos el reading más reciente. SQLite query directa para
        # evitar cargar el modelo completo si la tabla es grande.
        conn = deps.factory.get_connection()
        cur = conn.execute(
            "SELECT MAX(observed_at) FROM sensor_data"
        )
        row = cur.fetchone()
        last_obs_raw = row[0] if row else None

        if last_obs_raw:
            last_dt = datetime.fromisoformat(last_obs_raw)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - last_dt).total_seconds()
            from yvy.cli.formatting import fmt_duration

            # Si pasaron más de 5 minutos sin reading, warn
            if age < 300:
                status = "ok"
            elif age < 3600:
                status = "warn"
            else:
                status = "fail"
                overall_ok = False

            checks.append({
                "name": "Último reading sensor",
                "status": status,
                "detail": f"hace {fmt_duration(age)}",
                "value": {"timestamp": last_obs_raw, "age_seconds": age},
            })
        else:
            checks.append({
                "name": "Último reading sensor",
                "status": "warn",
                "detail": "ningún reading registrado todavía",
                "value": None,
            })
    except Exception as exc:
        checks.append({
            "name": "Último reading sensor",
            "status": "fail",
            "detail": f"error consultando DB: {exc}",
            "value": None,
        })

    # 3. Sync agent: hay credentials?
    creds_path = deps.root / "data" / "station_credentials.json"
    server_url = deps.app_config_repo.get("sync_server_url")

    if creds_path.exists() and server_url:
        checks.append({
            "name": "Sync agent",
            "status": "ok",
            "detail": "credentials presentes + server configurado",
            "value": {"server_url": server_url, "credentials_path": str(creds_path)},
        })
    elif not server_url:
        checks.append({
            "name": "Sync agent",
            "status": "warn",
            "detail": "sync_server_url no configurado",
            "value": None,
        })
    elif not creds_path.exists():
        checks.append({
            "name": "Sync agent",
            "status": "warn",
            "detail": "credentials no presentes",
            "value": None,
        })

    # 4. Cola sync por status
    try:
        counts = deps.sync_repo.count_by_status()
        pending = counts.get(SyncStatus.PENDING, 0)
        sending = counts.get(SyncStatus.SENDING, 0)
        sent = counts.get(SyncStatus.SENT, 0)
        error = counts.get(SyncStatus.ERROR, 0)

        if error > 0 or pending > 100:
            queue_status = "warn"
        else:
            queue_status = "ok"

        detail = (
            f"{pending} pending · {sending} sending · "
            f"{sent} sent · {error} error"
        )
        checks.append({
            "name": "Cola sync",
            "status": queue_status,
            "detail": detail,
            "value": {
                "pending": pending, "sending": sending,
                "sent": sent, "error": error,
            },
        })
    except Exception as exc:
        checks.append({
            "name": "Cola sync",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    summary = "OK" if overall_ok else "con avisos"
    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": [],
        "summary": f"Estado general: {summary}",
    }


# ─── info: identidad del nodo ────────────────────────────────────────────


def compute_info(deps: CoreDependencies) -> dict[str, Any]:
    """Info estática del nodo: identidad + recursos."""
    from yvy import __version__
    from yvy.cli.formatting import fmt_bytes

    checks: list[dict[str, Any]] = []

    # Version
    checks.append({
        "name": "Versión",
        "status": "info",
        "detail": __version__,
        "value": __version__,
    })

    # station_uuid
    if deps.station_uuid:
        checks.append({
            "name": "Station UUID",
            "status": "info",
            "detail": str(deps.station_uuid),
            "value": str(deps.station_uuid),
        })
    else:
        checks.append({
            "name": "Station UUID",
            "status": "warn",
            "detail": "no configurado",
            "value": None,
        })

    # IEA name — guardada por el wizard como "school_name"
    iea_name = deps.app_config_repo.get("school_name") or "no configurado"
    checks.append({
        "name": "IEA",
        "status": "info",
        "detail": iea_name,
        "value": iea_name,
    })

    # CUE — guardada por el wizard como "cue"
    cue = deps.app_config_repo.get("cue") or "no configurado"
    checks.append({
        "name": "CUE",
        "status": "info",
        "detail": cue,
        "value": cue,
    })

    # Server URL
    server_url = deps.app_config_repo.get("sync_server_url") or "no configurado"
    checks.append({
        "name": "Server URL",
        "status": "info",
        "detail": server_url,
        "value": server_url,
    })

    # Disco libre
    try:
        usage = shutil.disk_usage(deps.root)
        pct_used = (usage.used / usage.total) * 100
        disk_status = "ok"
        if pct_used > 90:
            disk_status = "fail"
        elif pct_used > 75:
            disk_status = "warn"
        checks.append({
            "name": "Disco",
            "status": disk_status,
            "detail": (
                f"{fmt_bytes(usage.free)} libre de {fmt_bytes(usage.total)} "
                f"({pct_used:.1f}% usado)"
            ),
            "value": {
                "total": usage.total, "used": usage.used,
                "free": usage.free, "pct_used": pct_used,
            },
        })
    except Exception as exc:
        checks.append({
            "name": "Disco",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    return {
        "ok": True,
        "checks": checks,
        "notes": [],
        "summary": f"YVY Edge v{__version__}",
    }


# ─── test sensor ─────────────────────────────────────────────────────────


# VID/PID del WH1081 (Fine Offset). Confirmado en VALIDAR_SENSOR.bat.
_WH1081_VID = 0x1941
_WH1081_PID = 0x8021


def test_sensor() -> dict[str, Any]:
    """Verifica USB sin abrir conexión pywws (nivel B).

    Comprobaciones:
      1. pywws importable.
      2. pyusb importable.
      3. libusb backend disponible.
      4. Device WH1081 detectable por VID/PID.

    NO lee frames del sensor (eso requiere comunicación activa y
    puede colisionar con SensorCollectorDaemon en runtime).
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. pywws
    try:
        import pywws  # noqa: F401
        checks.append({
            "name": "pywws",
            "status": "ok",
            "detail": "importable",
            "value": True,
        })
    except ImportError as exc:
        overall_ok = False
        checks.append({
            "name": "pywws",
            "status": "fail",
            "detail": f"no importable: {exc}",
            "value": False,
        })

    # 2. pyusb
    try:
        import usb.core
        checks.append({
            "name": "pyusb",
            "status": "ok",
            "detail": "importable",
            "value": True,
        })
    except ImportError as exc:
        overall_ok = False
        checks.append({
            "name": "pyusb",
            "status": "fail",
            "detail": f"no importable: {exc}",
            "value": False,
        })
        # Sin pyusb no podemos seguir con los otros checks
        return {
            "ok": False, "checks": checks, "notes": [
                "Ejecutar VALIDAR_SENSOR.bat para diagnóstico detallado.",
            ],
            "summary": "Sensor: pyusb no disponible",
        }

    # 3. backend libusb
    try:
        import usb.backend.libusb1 as libusb1
        backend = libusb1.get_backend()
        if backend is None:
            overall_ok = False
            checks.append({
                "name": "libusb backend",
                "status": "fail",
                "detail": "backend no encontrado (instalar libusb1.dll / Zadig)",
                "value": None,
            })
        else:
            checks.append({
                "name": "libusb backend",
                "status": "ok",
                "detail": "disponible",
                "value": True,
            })
    except Exception as exc:
        overall_ok = False
        checks.append({
            "name": "libusb backend",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    # 4. Detectar device por VID/PID
    try:
        import usb.core
        device = usb.core.find(idVendor=_WH1081_VID, idProduct=_WH1081_PID)
        if device is None:
            overall_ok = False
            checks.append({
                "name": "WH1081 detectado",
                "status": "fail",
                "detail": f"VID:{_WH1081_VID:04x} PID:{_WH1081_PID:04x} no encontrado",
                "value": False,
            })
        else:
            checks.append({
                "name": "WH1081 detectado",
                "status": "ok",
                "detail": f"VID:{_WH1081_VID:04x} PID:{_WH1081_PID:04x}",
                "value": True,
            })
    except Exception as exc:
        overall_ok = False
        checks.append({
            "name": "WH1081 detectado",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    notes = []
    if not overall_ok:
        notes.append(
            "Si el sensor no se detecta, verificar cable USB y driver Zadig "
            "(reemplazar driver por WinUSB)."
        )

    summary = "Sensor OK" if overall_ok else "Sensor con problemas"
    return {
        "ok": overall_ok, "checks": checks, "notes": notes, "summary": summary,
    }


# ─── test db ─────────────────────────────────────────────────────────────


def test_db(deps: CoreDependencies) -> dict[str, Any]:
    """Verifica que la DB esté accesible y consistente.

    Comprobaciones:
      1. Archivo DB existe.
      2. Se puede abrir y hacer SELECT.
      3. Schema version (tabla schema_versions o equivalente).
      4. Singleton sync_agent_state existe (migración v13 aplicada).
      5. Tablas críticas tienen counts esperables.
    """
    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. archivo
    if not deps.db_path.exists():
        return {
            "ok": False,
            "checks": [{
                "name": "Archivo DB",
                "status": "fail",
                "detail": f"{deps.db_path} no existe",
                "value": None,
            }],
            "notes": ["Ejecutar el launcher principal para crear la DB."],
            "summary": "DB inexistente",
        }
    checks.append({
        "name": "Archivo DB",
        "status": "ok",
        "detail": str(deps.db_path),
        "value": str(deps.db_path),
    })

    # 2. Conexión y SELECT trivial
    try:
        conn = deps.factory.get_connection()
        conn.execute("SELECT 1").fetchone()
        checks.append({
            "name": "Conexión",
            "status": "ok",
            "detail": "SELECT 1 ok",
            "value": True,
        })
    except Exception as exc:
        return {
            "ok": False,
            "checks": checks + [{
                "name": "Conexión",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }],
            "notes": [],
            "summary": "DB no accesible",
        }

    # 3. Migración v13 aplicada (sync_agent_state singleton)
    try:
        state = deps.sync_agent_state_repo.get_state()
        checks.append({
            "name": "Migración v13",
            "status": "ok",
            "detail": f"sync_agent_state OK (state={state.state.value})",
            "value": state.state.value,
        })
    except Exception as exc:
        overall_ok = False
        checks.append({
            "name": "Migración v13",
            "status": "fail",
            "detail": f"singleton no encontrado: {exc}",
            "value": None,
        })

    # 4. Counts críticos
    try:
        conn = deps.factory.get_connection()
        sensor_count = conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
        empirical_count = conn.execute("SELECT COUNT(*) FROM empirical_observation").fetchone()[0]
        queue_count = deps.sync_repo.count()

        checks.append({
            "name": "sensor_data",
            "status": "info",
            "detail": f"{sensor_count} filas",
            "value": sensor_count,
        })
        checks.append({
            "name": "empirical_observation",
            "status": "info",
            "detail": f"{empirical_count} filas",
            "value": empirical_count,
        })
        checks.append({
            "name": "sync_queue",
            "status": "info",
            "detail": f"{queue_count} filas",
            "value": queue_count,
        })
    except Exception as exc:
        overall_ok = False
        checks.append({
            "name": "Conteos de tablas",
            "status": "fail",
            "detail": f"error: {exc}",
            "value": None,
        })

    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": [],
        "summary": "DB OK" if overall_ok else "DB con problemas",
    }


# ─── test sync ───────────────────────────────────────────────────────────


def test_sync(deps: CoreDependencies, *, timeout_s: float = 5.0) -> dict[str, Any]:
    """Valida configuración + conectividad al server.

    Comprobaciones:
      1. data/station_credentials.json existe y parsea.
      2. Campos requeridos: station_uuid, key_version, key_hmac_hex.
      3. key_hmac_hex >= 64 chars (32 bytes).
      4. sync_server_url configurada en app_config.
      5. Cross-check: station_uuid de credentials == app_config.
      6. GET <sync_server_url>/healthz con timeout.

    NO firma envelope ni intenta /api/v1/ingest. Para eso está el
    smoke E2E (Paso 9), que requiere credentials reales del station
    autorizadas en el server.
    """
    import json as _json
    from uuid import UUID

    import httpx

    checks: list[dict[str, Any]] = []
    overall_ok = True

    # 1. credentials.json
    creds_path = deps.root / "data" / "station_credentials.json"
    if not creds_path.exists():
        return {
            "ok": False,
            "checks": [{
                "name": "Credentials JSON",
                "status": "fail",
                "detail": f"{creds_path.name} no existe",
                "value": None,
            }],
            "notes": [
                "Generar credentials con el CLI del server YVY Core: "
                "`yvy-server create-station -o credentials.json`",
                "Luego copiar el archivo a data/station_credentials.json.",
            ],
            "summary": "Sync no configurado (sin credentials)",
        }

    try:
        creds = _json.loads(creds_path.read_text(encoding="utf-8-sig"))
        checks.append({
            "name": "Credentials JSON",
            "status": "ok",
            "detail": "presente, parsea",
            "value": str(creds_path),
        })
    except Exception as exc:
        return {
            "ok": False,
            "checks": [{
                "name": "Credentials JSON",
                "status": "fail",
                "detail": f"parse error: {exc}",
                "value": None,
            }],
            "notes": [],
            "summary": "Credentials JSON corrupto",
        }

    # 2-3. Formato
    cred_station_uuid: UUID | None = None
    try:
        cred_station_uuid = UUID(creds["station_uuid"])
        key_version = int(creds["key_version"])
        key_hex = creds["key_hmac_hex"]
        key_bytes = bytes.fromhex(key_hex)
        if len(key_bytes) < 32:
            raise ValueError(f"key_hmac_hex muy corto ({len(key_bytes)} bytes < 32)")
        checks.append({
            "name": "Formato credentials",
            "status": "ok",
            "detail": f"uuid + key v{key_version} + {len(key_bytes)} bytes",
            "value": {
                "station_uuid": str(cred_station_uuid),
                "key_version": key_version,
                "key_length_bytes": len(key_bytes),
            },
        })
    except (KeyError, ValueError, TypeError) as exc:
        return {
            "ok": False,
            "checks": checks + [{
                "name": "Formato credentials",
                "status": "fail",
                "detail": f"{type(exc).__name__}: {exc}",
                "value": None,
            }],
            "notes": [],
            "summary": "Credentials con formato inválido",
        }

    # 4. server_url
    server_url = deps.app_config_repo.get("sync_server_url")
    if not server_url:
        return {
            "ok": False,
            "checks": checks + [{
                "name": "URL del server",
                "status": "fail",
                "detail": "sync_server_url no configurado en app_config",
                "value": None,
            }],
            "notes": [
                "Configurar con: `app_config_repo.set('sync_server_url', "
                "'https://...')`",
            ],
            "summary": "Server URL no configurada",
        }
    checks.append({
        "name": "URL del server",
        "status": "ok",
        "detail": server_url,
        "value": server_url,
    })

    # 5. Cross-check station_uuid
    if deps.station_uuid is not None and deps.station_uuid != cred_station_uuid:
        overall_ok = False
        checks.append({
            "name": "Cross-check UUIDs",
            "status": "fail",
            "detail": (
                f"credentials={cred_station_uuid} ≠ "
                f"app_config={deps.station_uuid}"
            ),
            "value": False,
        })
        return {
            "ok": False,
            "checks": checks,
            "notes": [
                "Mismatch de seguridad: agent NO arrancará. "
                "Verificar que las credentials correspondan a esta station.",
            ],
            "summary": "UUIDs no coinciden",
        }
    checks.append({
        "name": "Cross-check UUIDs",
        "status": "ok",
        "detail": "credentials = app_config",
        "value": True,
    })

    # 6. GET /healthz
    healthz_url = server_url.rstrip("/") + "/healthz"
    try:
        with httpx.Client(timeout=timeout_s, verify=True) as client:
            response = client.get(healthz_url)

        if response.status_code == 200:
            checks.append({
                "name": "Conectividad server",
                "status": "ok",
                "detail": f"GET /healthz → 200 OK ({response.elapsed.total_seconds()*1000:.0f}ms)",
                "value": {
                    "status_code": 200,
                    "elapsed_ms": response.elapsed.total_seconds() * 1000,
                },
            })
        elif response.status_code == 404:
            overall_ok = False
            checks.append({
                "name": "Conectividad server",
                "status": "warn",
                "detail": "GET /healthz → 404 (¿endpoint distinto?)",
                "value": {"status_code": 404},
            })
        else:
            overall_ok = False
            checks.append({
                "name": "Conectividad server",
                "status": "warn",
                "detail": f"GET /healthz → {response.status_code}",
                "value": {"status_code": response.status_code},
            })
    except httpx.ConnectTimeout:
        overall_ok = False
        checks.append({
            "name": "Conectividad server",
            "status": "fail",
            "detail": f"timeout ({timeout_s}s) — server no responde",
            "value": None,
        })
    except httpx.ConnectError as exc:
        overall_ok = False
        checks.append({
            "name": "Conectividad server",
            "status": "fail",
            "detail": f"no se pudo conectar: {exc}",
            "value": None,
        })
    except (httpx.HTTPError, OSError) as exc:
        overall_ok = False
        checks.append({
            "name": "Conectividad server",
            "status": "fail",
            "detail": f"{type(exc).__name__}: {exc}",
            "value": None,
        })

    notes = []
    if not overall_ok:
        notes.append("Verificá que el server esté arriba y que la red llegue.")

    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": notes,
        "summary": "Sync ready" if overall_ok else "Sync con problemas",
    }


# ─── check-updates ───────────────────────────────────────────────────────


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


# ─── update status ───────────────────────────────────────────────────────


def compute_update_status(deps: CoreDependencies) -> dict[str, Any]:
    """Estado del sistema de updates: versión, slots, releases, pending."""
    from yvy import __version__
    from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
        SQLiteAuditLogRepository,
    )
    from yvy.infrastructure.updates.installer import UpdateInstaller

    checks: list[dict[str, Any]] = []
    audit_repo = SQLiteAuditLogRepository(deps.factory)
    installer = UpdateInstaller(
        app_config_repo=deps.app_config_repo,
        audit_repo=audit_repo,
        root_path=deps.root,
    )

    checks.append({
        "name": "Versión instalada",
        "status": "info",
        "detail": __version__,
        "value": __version__,
    })

    current = deps.app_config_repo.get_current_release()
    previous = deps.app_config_repo.get_previous_release()
    stable = deps.app_config_repo.get_last_stable_release()

    if current:
        checks.append({
            "name": "Release actual (current)",
            "status": "info",
            "detail": current,
            "value": current,
        })
        if previous:
            checks.append({
                "name": "Release anterior (previous)",
                "status": "info",
                "detail": previous,
                "value": previous,
            })
        if stable:
            checks.append({
                "name": "Último estable (last_stable)",
                "status": "info",
                "detail": stable,
                "value": stable,
            })
    else:
        checks.append({
            "name": "Modo de instalación",
            "status": "warn",
            "detail": "flat (sin slots — primera actualización migrará automáticamente)",
            "value": "flat",
        })

    releases = installer.get_releases_on_disk()
    if releases:
        details = "  ·  ".join(
            f"{r['version']}"
            + (f" ({', '.join(r['states'])})" if r["states"] else "")
            for r in releases
        )
        checks.append({
            "name": "Releases en disco",
            "status": "info",
            "detail": details,
            "value": [{"version": r["version"], "states": r["states"]} for r in releases],
        })

    pending = deps.app_config_repo.get_pending_update()
    if pending:
        to_ver = pending.get("edge_version", "?")
        is_dl = deps.app_config_repo.is_update_downloaded()
        dl_label = "descargado ✓" if is_dl else "pendiente de descarga"
        size_mb = pending.get("package_size_bytes", 0) / (1024 * 1024)
        checks.append({
            "name": "Actualización disponible",
            "status": "ok" if is_dl else "warn",
            "detail": f"v{to_ver}  {size_mb:.1f} MB  ({dl_label})",
            "value": {"version": to_ver, "is_downloaded": is_dl},
        })
    else:
        checks.append({
            "name": "Actualización disponible",
            "status": "ok",
            "detail": "al día — no hay updates pendientes",
            "value": None,
        })

    install_status = deps.app_config_repo.get_install_status()
    if install_status and install_status not in ("completed", "failed"):
        to_v = deps.app_config_repo.get_install_to_version() or "?"
        checks.append({
            "name": "Instalación en curso",
            "status": "warn",
            "detail": f"estado={install_status}  destino={to_v}",
            "value": {"status": install_status, "to_version": to_v},
        })

    return {
        "ok": True,
        "checks": checks,
        "notes": [],
        "summary": f"YVY Edge v{__version__}",
    }


# ─── update install ──────────────────────────────────────────────────────


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
    from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
        SQLiteAuditLogRepository,
    )
    from yvy.infrastructure.updates.installer import UpdateInstaller

    audit_repo = SQLiteAuditLogRepository(deps.factory)
    installer = UpdateInstaller(
        app_config_repo=deps.app_config_repo,
        audit_repo=audit_repo,
        root_path=deps.root,
    )

    pre = installer.prevalidate()
    if not pre.ok:
        return {
            "ok": False,
            "prevalidation_ok": False,
            "reason": pre.reason,
            "launched": False,
            "error": None,
        }

    try:
        installer.request_install(requested_by_user_id=None)
    except RuntimeError as exc:
        return {
            "ok": False,
            "prevalidation_ok": True,
            "reason": None,
            "launched": False,
            "error": str(exc),
        }

    return {
        "ok": True,
        "prevalidation_ok": True,
        "reason": None,
        "launched": True,
        "error": None,
    }


# ─── rollback ────────────────────────────────────────────────────────────


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
    from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
        SQLiteAuditLogRepository,
    )
    from yvy.infrastructure.updates.installer import UpdateInstaller

    audit_repo = SQLiteAuditLogRepository(deps.factory)
    installer = UpdateInstaller(
        app_config_repo=deps.app_config_repo,
        audit_repo=audit_repo,
        root_path=deps.root,
    )

    result = installer.rollback(
        to_version=to_version,
        reason=reason,
        performed_by=None,
    )
    return {
        "ok": result.ok,
        "to_version": result.to_version,
        "reason": result.reason,
    }


# ─── update mark-stable ──────────────────────────────────────────────────


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
    from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
        SQLiteAuditLogRepository,
    )
    from yvy.infrastructure.updates.retention import ReleaseRetention

    releases_dir = deps.root / "releases"
    audit_repo = SQLiteAuditLogRepository(deps.factory)
    retention = ReleaseRetention(
        app_config_repo=deps.app_config_repo,
        audit_repo=audit_repo,
        releases_dir=releases_dir,
    )

    try:
        retention.mark_stable_manual(version=version, user_id=None)
    except Exception as exc:
        return {"ok": False, "version": version, "error": str(exc)}

    return {"ok": True, "version": version, "error": None}


# ─── configure-sync: setear credentials (idempotente) ─────────────────────


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
            "ok": False, "skipped": False, "reason": "no_server_url",
            "station_uuid": None, "server_url": None, "dest_path": None,
            "error": "Falta la URL del servidor (--server-url o YVY_SYNC_URL).",
            "notes": [],
        }

    if not creds_path.exists():
        return {
            "ok": False, "skipped": False, "reason": "creds_not_found",
            "station_uuid": None, "server_url": None, "dest_path": None,
            "error": f"No se encontró el archivo de credentials: {creds_path}",
            "notes": [],
        }

    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False, "skipped": False, "reason": "creds_invalid_json",
            "station_uuid": None, "server_url": None, "dest_path": None,
            "error": f"el archivo no es JSON válido: {exc}", "notes": [],
        }

    err = _validate_credentials_dict(creds)
    if err:
        return {
            "ok": False, "skipped": False, "reason": "creds_invalid",
            "station_uuid": None, "server_url": None, "dest_path": None,
            "error": f"credentials inválidas — {err}", "notes": [],
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
        "ok": True, "skipped": False, "reason": "configured",
        "station_uuid": station_uuid, "server_url": url, "dest_path": str(dest),
        "error": None, "notes": notes,
    }
