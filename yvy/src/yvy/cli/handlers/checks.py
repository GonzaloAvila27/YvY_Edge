"""Handlers de verificación: ``test sensor`` / ``test db`` / ``test sync``."""

from __future__ import annotations

import logging
from typing import Any

from yvy.bootstrap import CoreDependencies

logger = logging.getLogger(__name__)

# VID/PID del WH1081 (Fine Offset). Confirmado en VALIDAR_SENSOR.bat.
# NUNCA hacer "Replace Driver" sobre un dispositivo que no coincida con estos:
# podría ser el teclado o el mouse.
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

        checks.append(
            {
                "name": "pywws",
                "status": "ok",
                "detail": "importable",
                "value": True,
            }
        )
    except ImportError as exc:
        overall_ok = False
        checks.append(
            {
                "name": "pywws",
                "status": "fail",
                "detail": f"no importable: {exc}",
                "value": False,
            }
        )

    # 2. pyusb
    try:
        import usb.core

        checks.append(
            {
                "name": "pyusb",
                "status": "ok",
                "detail": "importable",
                "value": True,
            }
        )
    except ImportError as exc:
        overall_ok = False
        checks.append(
            {
                "name": "pyusb",
                "status": "fail",
                "detail": f"no importable: {exc}",
                "value": False,
            }
        )
        # Sin pyusb no podemos seguir con los otros checks
        return {
            "ok": False,
            "checks": checks,
            "notes": [
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
            checks.append(
                {
                    "name": "libusb backend",
                    "status": "fail",
                    "detail": "backend no encontrado (instalar libusb1.dll / Zadig)",
                    "value": None,
                }
            )
        else:
            checks.append(
                {
                    "name": "libusb backend",
                    "status": "ok",
                    "detail": "disponible",
                    "value": True,
                }
            )
    except Exception as exc:
        overall_ok = False
        checks.append(
            {
                "name": "libusb backend",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    # 4. Detectar device por VID/PID
    try:
        import usb.core

        device = usb.core.find(idVendor=_WH1081_VID, idProduct=_WH1081_PID)
        if device is None:
            overall_ok = False
            checks.append(
                {
                    "name": "WH1081 detectado",
                    "status": "fail",
                    "detail": f"VID:{_WH1081_VID:04x} PID:{_WH1081_PID:04x} no encontrado",
                    "value": False,
                }
            )
        else:
            checks.append(
                {
                    "name": "WH1081 detectado",
                    "status": "ok",
                    "detail": f"VID:{_WH1081_VID:04x} PID:{_WH1081_PID:04x}",
                    "value": True,
                }
            )
    except Exception as exc:
        overall_ok = False
        checks.append(
            {
                "name": "WH1081 detectado",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    notes = []
    if not overall_ok:
        notes.append(
            "Si el sensor no se detecta, verificar cable USB y driver Zadig "
            "(reemplazar driver por WinUSB)."
        )

    summary = "Sensor OK" if overall_ok else "Sensor con problemas"
    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": notes,
        "summary": summary,
    }


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
            "checks": [
                {
                    "name": "Archivo DB",
                    "status": "fail",
                    "detail": f"{deps.db_path} no existe",
                    "value": None,
                }
            ],
            "notes": ["Ejecutar el launcher principal para crear la DB."],
            "summary": "DB inexistente",
        }
    checks.append(
        {
            "name": "Archivo DB",
            "status": "ok",
            "detail": str(deps.db_path),
            "value": str(deps.db_path),
        }
    )

    # 2. Conexión y SELECT trivial
    try:
        conn = deps.factory.get_connection()
        conn.execute("SELECT 1").fetchone()
        checks.append(
            {
                "name": "Conexión",
                "status": "ok",
                "detail": "SELECT 1 ok",
                "value": True,
            }
        )
    except Exception as exc:
        return {
            "ok": False,
            "checks": [
                *checks,
                {"name": "Conexión", "status": "fail", "detail": f"error: {exc}", "value": None},
            ],
            "notes": [],
            "summary": "DB no accesible",
        }

    # 3. Migración v13 aplicada (sync_agent_state singleton)
    try:
        state = deps.sync_agent_state_repo.get_state()
        checks.append(
            {
                "name": "Migración v13",
                "status": "ok",
                "detail": f"sync_agent_state OK (state={state.state.value})",
                "value": state.state.value,
            }
        )
    except Exception as exc:
        overall_ok = False
        checks.append(
            {
                "name": "Migración v13",
                "status": "fail",
                "detail": f"singleton no encontrado: {exc}",
                "value": None,
            }
        )

    # 4. Counts críticos
    try:
        conn = deps.factory.get_connection()
        sensor_count = conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
        empirical_count = conn.execute("SELECT COUNT(*) FROM empirical_observation").fetchone()[0]
        queue_count = deps.sync_repo.count()

        checks.append(
            {
                "name": "sensor_data",
                "status": "info",
                "detail": f"{sensor_count} filas",
                "value": sensor_count,
            }
        )
        checks.append(
            {
                "name": "empirical_observation",
                "status": "info",
                "detail": f"{empirical_count} filas",
                "value": empirical_count,
            }
        )
        checks.append(
            {
                "name": "sync_queue",
                "status": "info",
                "detail": f"{queue_count} filas",
                "value": queue_count,
            }
        )
    except Exception as exc:
        overall_ok = False
        checks.append(
            {
                "name": "Conteos de tablas",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": [],
        "summary": "DB OK" if overall_ok else "DB con problemas",
    }


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
            "checks": [
                {
                    "name": "Credentials JSON",
                    "status": "fail",
                    "detail": f"{creds_path.name} no existe",
                    "value": None,
                }
            ],
            "notes": [
                "Generar credentials con el CLI del server YVY Core: "
                "`yvy-server create-station -o credentials.json`",
                "Luego copiar el archivo a data/station_credentials.json.",
            ],
            "summary": "Sync no configurado (sin credentials)",
        }

    try:
        creds = _json.loads(creds_path.read_text(encoding="utf-8-sig"))
        checks.append(
            {
                "name": "Credentials JSON",
                "status": "ok",
                "detail": "presente, parsea",
                "value": str(creds_path),
            }
        )
    except Exception as exc:
        return {
            "ok": False,
            "checks": [
                {
                    "name": "Credentials JSON",
                    "status": "fail",
                    "detail": f"parse error: {exc}",
                    "value": None,
                }
            ],
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
        checks.append(
            {
                "name": "Formato credentials",
                "status": "ok",
                "detail": f"uuid + key v{key_version} + {len(key_bytes)} bytes",
                "value": {
                    "station_uuid": str(cred_station_uuid),
                    "key_version": key_version,
                    "key_length_bytes": len(key_bytes),
                },
            }
        )
    except (KeyError, ValueError, TypeError) as exc:
        return {
            "ok": False,
            "checks": [
                *checks,
                {
                    "name": "Formato credentials",
                    "status": "fail",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "value": None,
                },
            ],
            "notes": [],
            "summary": "Credentials con formato inválido",
        }

    # 4. server_url
    server_url = deps.app_config_repo.get("sync_server_url")
    if not server_url:
        return {
            "ok": False,
            "checks": [
                *checks,
                {
                    "name": "URL del server",
                    "status": "fail",
                    "detail": "sync_server_url no configurado en app_config",
                    "value": None,
                },
            ],
            "notes": [
                "Configurar con: `app_config_repo.set('sync_server_url', " "'https://...')`",
            ],
            "summary": "Server URL no configurada",
        }
    checks.append(
        {
            "name": "URL del server",
            "status": "ok",
            "detail": server_url,
            "value": server_url,
        }
    )

    # 5. Cross-check station_uuid
    if deps.station_uuid is not None and deps.station_uuid != cred_station_uuid:
        overall_ok = False
        checks.append(
            {
                "name": "Cross-check UUIDs",
                "status": "fail",
                "detail": (f"credentials={cred_station_uuid} ≠ " f"app_config={deps.station_uuid}"),
                "value": False,
            }
        )
        return {
            "ok": False,
            "checks": checks,
            "notes": [
                "Mismatch de seguridad: agent NO arrancará. "
                "Verificar que las credentials correspondan a esta station.",
            ],
            "summary": "UUIDs no coinciden",
        }
    checks.append(
        {
            "name": "Cross-check UUIDs",
            "status": "ok",
            "detail": "credentials = app_config",
            "value": True,
        }
    )

    # 6. GET /healthz
    healthz_url = server_url.rstrip("/") + "/healthz"
    try:
        with httpx.Client(timeout=timeout_s, verify=True) as client:
            response = client.get(healthz_url)

        if response.status_code == 200:
            checks.append(
                {
                    "name": "Conectividad server",
                    "status": "ok",
                    "detail": f"GET /healthz → 200 OK ({response.elapsed.total_seconds()*1000:.0f}ms)",
                    "value": {
                        "status_code": 200,
                        "elapsed_ms": response.elapsed.total_seconds() * 1000,
                    },
                }
            )
        elif response.status_code == 404:
            overall_ok = False
            checks.append(
                {
                    "name": "Conectividad server",
                    "status": "warn",
                    "detail": "GET /healthz → 404 (¿endpoint distinto?)",
                    "value": {"status_code": 404},
                }
            )
        else:
            overall_ok = False
            checks.append(
                {
                    "name": "Conectividad server",
                    "status": "warn",
                    "detail": f"GET /healthz → {response.status_code}",
                    "value": {"status_code": response.status_code},
                }
            )
    except httpx.ConnectTimeout:
        overall_ok = False
        checks.append(
            {
                "name": "Conectividad server",
                "status": "fail",
                "detail": f"timeout ({timeout_s}s) — server no responde",
                "value": None,
            }
        )
    except httpx.ConnectError as exc:
        overall_ok = False
        checks.append(
            {
                "name": "Conectividad server",
                "status": "fail",
                "detail": f"no se pudo conectar: {exc}",
                "value": None,
            }
        )
    except (httpx.HTTPError, OSError) as exc:
        overall_ok = False
        checks.append(
            {
                "name": "Conectividad server",
                "status": "fail",
                "detail": f"{type(exc).__name__}: {exc}",
                "value": None,
            }
        )

    notes = []
    if not overall_ok:
        notes.append("Verificá que el server esté arriba y que la red llegue.")

    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": notes,
        "summary": "Sync ready" if overall_ok else "Sync con problemas",
    }
