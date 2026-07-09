"""Handlers de diagnóstico del nodo: ``status`` e ``info``."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from typing import Any

from yvy.bootstrap import CoreDependencies
from yvy.domain.sync.enums import SyncStatus

logger = logging.getLogger(__name__)


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

        checks.append(
            {
                "name": "Base de datos",
                "status": "ok",
                "detail": f"{deps.db_path.name} ({fmt_bytes(db_size)})",
                "value": {"path": str(deps.db_path), "size_bytes": db_size},
            }
        )
    except Exception as exc:
        overall_ok = False
        checks.append(
            {
                "name": "Base de datos",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    # 2. Último sensor reading
    try:
        # Buscamos el reading más reciente. SQLite query directa para
        # evitar cargar el modelo completo si la tabla es grande.
        conn = deps.factory.get_connection()
        cur = conn.execute("SELECT MAX(observed_at) FROM sensor_data")
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

            checks.append(
                {
                    "name": "Último reading sensor",
                    "status": status,
                    "detail": f"hace {fmt_duration(age)}",
                    "value": {"timestamp": last_obs_raw, "age_seconds": age},
                }
            )
        else:
            checks.append(
                {
                    "name": "Último reading sensor",
                    "status": "warn",
                    "detail": "ningún reading registrado todavía",
                    "value": None,
                }
            )
    except Exception as exc:
        checks.append(
            {
                "name": "Último reading sensor",
                "status": "fail",
                "detail": f"error consultando DB: {exc}",
                "value": None,
            }
        )

    # 3. Sync agent: hay credentials?
    creds_path = deps.root / "data" / "station_credentials.json"
    server_url = deps.app_config_repo.get("sync_server_url")

    if creds_path.exists() and server_url:
        checks.append(
            {
                "name": "Sync agent",
                "status": "ok",
                "detail": "credentials presentes + server configurado",
                "value": {"server_url": server_url, "credentials_path": str(creds_path)},
            }
        )
    elif not server_url:
        checks.append(
            {
                "name": "Sync agent",
                "status": "warn",
                "detail": "sync_server_url no configurado",
                "value": None,
            }
        )
    elif not creds_path.exists():
        checks.append(
            {
                "name": "Sync agent",
                "status": "warn",
                "detail": "credentials no presentes",
                "value": None,
            }
        )

    # 4. Cola sync por status
    try:
        counts = deps.sync_repo.count_by_status()
        pending = counts.get(SyncStatus.PENDING, 0)
        sending = counts.get(SyncStatus.SENDING, 0)
        sent = counts.get(SyncStatus.SENT, 0)
        error = counts.get(SyncStatus.ERROR, 0)

        queue_status = "warn" if error > 0 or pending > 100 else "ok"

        detail = f"{pending} pending · {sending} sending · " f"{sent} sent · {error} error"
        checks.append(
            {
                "name": "Cola sync",
                "status": queue_status,
                "detail": detail,
                "value": {
                    "pending": pending,
                    "sending": sending,
                    "sent": sent,
                    "error": error,
                },
            }
        )
    except Exception as exc:
        checks.append(
            {
                "name": "Cola sync",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    summary = "OK" if overall_ok else "con avisos"
    return {
        "ok": overall_ok,
        "checks": checks,
        "notes": [],
        "summary": f"Estado general: {summary}",
    }


def compute_info(deps: CoreDependencies) -> dict[str, Any]:
    """Info estática del nodo: identidad + recursos."""
    from yvy import __version__
    from yvy.cli.formatting import fmt_bytes

    checks: list[dict[str, Any]] = []

    # Version
    checks.append(
        {
            "name": "Versión",
            "status": "info",
            "detail": __version__,
            "value": __version__,
        }
    )

    # station_uuid
    if deps.station_uuid:
        checks.append(
            {
                "name": "Station UUID",
                "status": "info",
                "detail": str(deps.station_uuid),
                "value": str(deps.station_uuid),
            }
        )
    else:
        checks.append(
            {
                "name": "Station UUID",
                "status": "warn",
                "detail": "no configurado",
                "value": None,
            }
        )

    # IEA name — guardada por el wizard como "school_name"
    iea_name = deps.app_config_repo.get("school_name") or "no configurado"
    checks.append(
        {
            "name": "IEA",
            "status": "info",
            "detail": iea_name,
            "value": iea_name,
        }
    )

    # CUE — guardada por el wizard como "cue"
    cue = deps.app_config_repo.get("cue") or "no configurado"
    checks.append(
        {
            "name": "CUE",
            "status": "info",
            "detail": cue,
            "value": cue,
        }
    )

    # Server URL
    server_url = deps.app_config_repo.get("sync_server_url") or "no configurado"
    checks.append(
        {
            "name": "Server URL",
            "status": "info",
            "detail": server_url,
            "value": server_url,
        }
    )

    # Disco libre
    try:
        usage = shutil.disk_usage(deps.root)
        pct_used = (usage.used / usage.total) * 100
        disk_status = "ok"
        if pct_used > 90:
            disk_status = "fail"
        elif pct_used > 75:
            disk_status = "warn"
        checks.append(
            {
                "name": "Disco",
                "status": disk_status,
                "detail": (
                    f"{fmt_bytes(usage.free)} libre de {fmt_bytes(usage.total)} "
                    f"({pct_used:.1f}% usado)"
                ),
                "value": {
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "pct_used": pct_used,
                },
            }
        )
    except Exception as exc:
        checks.append(
            {
                "name": "Disco",
                "status": "fail",
                "detail": f"error: {exc}",
                "value": None,
            }
        )

    return {
        "ok": True,
        "checks": checks,
        "notes": [],
        "summary": f"YVY Edge v{__version__}",
    }
