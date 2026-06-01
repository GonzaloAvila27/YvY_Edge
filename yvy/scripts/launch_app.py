"""Lanzador interactivo de YVY para exploración de UI.

Usa la DB de producción (data/yvy.sqlite). Si no tiene usuarios,
crea uno superadmin por defecto. Si no tiene station_uuid en app_config,
genera uno aleatorio (modo desarrollo).

Credenciales por defecto (si DB vacía):
    usuario:   director
    contraseña: director2026

Sync agent (Fase 9.2):
    Lee credentials de ``data/station_credentials.json`` (formato del
    server: {"station_uuid", "key_version", "key_hmac_hex"}).
    Lee server URL de ``app_config.get("sync_server_url")``.

    Si las credentials o la URL faltan, la app arranca normalmente pero
    sin sync agent. La UI muestra "Agent: no inicializado (sin
    credentials)". Esto es deliberado para soportar:
      - desarrollo local
      - troubleshooting de UI
      - deploys parciales
      - laboratorios sin server

Uso:
    python scripts/launch_app.py
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)-7s %(name)s : %(message)s",
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
from yvy.application.use_cases.admin.update_retention_policy import UpdateRetentionPolicyUseCase
from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.complete_onboarding import CompleteOnboardingUseCase
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.application.use_cases.auth.manage_user import SetUserActiveUseCase, ToggleExportFlagUseCase
from yvy.application.use_cases.empirical.create_empirical_event import CreateEmpiricalEventUseCase
from yvy.application.use_cases.empirical.create_empirical_observation import CreateEmpiricalObservationUseCase
from yvy.application.use_cases.empirical.list_get_observations import (
    GetObservationDetailsUseCase,
    ListEmpiricalObservationsUseCase,
)
from yvy.application.use_cases.query_sensor_aggregated import QuerySensorAggregatedUseCase
from yvy.application.use_cases.retention.run_retention_job import RunRetentionJobUseCase
from yvy.application.use_cases.sensor.capture_live_reading import CaptureLiveReadingUseCase
from yvy.application.use_cases.sensor.run_catchup_recovery import RunCatchupRecoveryUseCase
from yvy.domain.auth.enums import Role
from yvy.domain.retention.models import RetentionPolicy
from yvy.domain.shared.value_objects import StationUUID
from yvy.bootstrap import build_core_dependencies
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.help.help_repository import HelpRepository
from yvy.infrastructure.pywws.catchup_source import PywwsCatchupSource
from yvy.infrastructure.pywws.live_source import PywwsLiveSource
from yvy.infrastructure.pywws.parser import PywwsPayloadParser
from yvy.infrastructure.scheduling.sensor_collector import SensorCollectorDaemon
from yvy.infrastructure.sync.http_client import HttpClient
from yvy.infrastructure.sync.sync_agent import SyncAgentConfig, SyncAgentDaemon
from yvy.infrastructure.sync.update_checker_daemon import UpdateCheckerDaemon
from yvy.infrastructure.system.clock import SystemClock
from yvy.presentation.app import MainApplication
from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.empirical_controller import EmpiricalController
from yvy.presentation.controllers.sync_controller import SyncController
from yvy.presentation.controllers.users_admin_controller import UsersAdminController

TZ_AR = ZoneInfo("America/Argentina/Cordoba")

DEFAULT_USER = "director"
DEFAULT_PASS = "director2026"

STATION_CREDENTIALS_PATH = ROOT / "data" / "station_credentials.json"


def main() -> int:
    # Construir deps core vía bootstrap (compartido con CLI python -m yvy)
    deps = build_core_dependencies(root=ROOT)
    factory = deps.factory
    db_path = deps.db_path
    user_repo = deps.user_repo
    audit_repo = deps.audit_repo
    metrics_repo = deps.metrics_repo
    sensor_repo = deps.sensor_repo
    sync_repo = deps.sync_repo
    sync_agent_state_repo = deps.sync_agent_state_repo
    empirical_repo = deps.empirical_repo
    app_config_repo = deps.app_config_repo
    clock = deps.clock

    # Hasher solo lo usa el launcher (no es dep core)
    hasher = BcryptPasswordHasher(rounds=4)

    create_uc = CreateUserUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher)

    # Use case de onboarding — se pasa a MainApplication para que lo invoque
    # automáticamente en primer arranque.
    onboarding_uc = CompleteOnboardingUseCase(
        create_user_uc=create_uc,
        audit_repo=audit_repo,
        app_config_repo=app_config_repo,
        credentials_root=ROOT,
    )

    onboarding_done = app_config_repo.is_onboarding_completed()

    if onboarding_done:
        # Instalación existente: seed defensivo para compat dev.
        if app_config_repo.get("station_uuid") is None:
            dev_uuid = str(uuid.uuid4())
            app_config_repo.set("station_uuid", dev_uuid)
            print(f"[dev] station_uuid generado: {dev_uuid}")

        # Usuario de emergencia si la DB quedó sin usuarios (no debería pasar).
        users = user_repo.list_all()
        if not users:
            print(f"DB sin usuarios. Creando superadmin '{DEFAULT_USER}' / '{DEFAULT_PASS}'")
            create_uc.execute(
                username=DEFAULT_USER,
                full_name="Director IEA",
                password=DEFAULT_PASS,
                role=Role.SUPERADMIN,
                can_export_raw=True,
            )
        else:
            print(f"Usuarios existentes: {[u.username for u in users]}")
    else:
        # Primera instalación: el wizard se encargará de station_uuid y usuarios.
        # Seed temporal para que los use cases se puedan construir.
        if app_config_repo.get("station_uuid") is None:
            temp_uuid = str(uuid.uuid4())
            app_config_repo.set("station_uuid", temp_uuid)
            app_config_repo.set("station_uuid_is_temporary", "true")
            print(f"[onboarding] UUID temporal: {temp_uuid} (el wizard lo reemplazará)")
        print("[onboarding] Primera instalación — el wizard configurará la estación.")

    _station_uuid = StationUUID(uuid.UUID(app_config_repo.get("station_uuid")))
    _parser = PywwsPayloadParser()

    login_uc = LoginUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher, time_provider=clock)
    change_uc = ChangePasswordUseCase(user_repo=user_repo, audit_repo=audit_repo, hasher=hasher)
    set_active_uc = SetUserActiveUseCase(user_repo=user_repo, audit_repo=audit_repo)
    toggle_uc = ToggleExportFlagUseCase(user_repo=user_repo, audit_repo=audit_repo)
    list_logs_uc = ListAuditLogsUseCase(audit_repo=audit_repo)
    update_retention_uc = UpdateRetentionPolicyUseCase(metrics_repo=metrics_repo)
    export_data_uc = ExportDataCsvUseCase(factory=factory, audit_repo=audit_repo)
    export_raw_uc = ExportRawCsvUseCase(factory=factory, audit_repo=audit_repo)
    retention_uc = RunRetentionJobUseCase(
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        time_provider=clock,
        policy=RetentionPolicy.default(),
    )

    create_obs_uc = CreateEmpiricalObservationUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo,
        audit_repo=audit_repo,
        app_config=app_config_repo,
        time_provider=clock,
    )
    create_event_uc = CreateEmpiricalEventUseCase(
        empirical_repo=empirical_repo,
        sync_repo=sync_repo,
        audit_repo=audit_repo,
        app_config=app_config_repo,
        time_provider=clock,
    )
    list_obs_uc = ListEmpiricalObservationsUseCase(empirical_repo=empirical_repo)
    get_detail_uc = GetObservationDetailsUseCase(empirical_repo=empirical_repo)

    empirical_controller = EmpiricalController(
        create_observation_uc=create_obs_uc,
        create_event_uc=create_event_uc,
        list_observations_uc=list_obs_uc,
        get_observation_details_uc=get_detail_uc,
    )

    auth_controller = AuthController(login_use_case=login_uc, change_password_use_case=change_uc)

    def _actor_provider() -> int | None:
        u = auth_controller.current_user
        return u.id if u else None

    users_controller = UsersAdminController(
        user_repo=user_repo,
        create_user_uc=create_uc,
        change_password_uc=change_uc,
        set_active_uc=set_active_uc,
        toggle_export_uc=toggle_uc,
        actor_user_id_provider=_actor_provider,
    )

    # ── Sync + Update checker: wiring híbrido ────────────────────────────
    # Si faltan credentials → UI sigue funcional sin agent ni checker.
    sync_creds = _load_sync_credentials(app_config_repo)
    update_check_trigger = threading.Event()
    sync_agent: SyncAgentDaemon | None = None
    update_checker: UpdateCheckerDaemon | None = None

    if sync_creds:
        sync_agent = _try_build_sync_agent(
            app_config_repo=app_config_repo,
            sync_repo=sync_repo,
            sync_agent_state_repo=sync_agent_state_repo,
            time_provider=clock,
            http_client=sync_creds["http_client"],
            station_uuid=sync_creds["station_uuid"],
            key_version=sync_creds["key_version"],
            key_bytes=sync_creds["key_bytes"],
            update_check_trigger=update_check_trigger,
        )
        update_checker = _try_build_update_checker(
            app_config_repo=app_config_repo,
            http_client=sync_creds["http_client"],
            station_uuid=sync_creds["station_uuid"],
            key_version=sync_creds["key_version"],
            key_bytes=sync_creds["key_bytes"],
            trigger=update_check_trigger,
        )

    # Catchup use case (siempre se arma; no depende del agent)
    catchup_uc = RunCatchupRecoveryUseCase(
        catchup_source=PywwsCatchupSource(),
        sensor_repo=sensor_repo,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        station_uuid=_station_uuid,
        time_provider=clock,
        parser=_parser,
    )

    sync_controller = SyncController(
        catchup_use_case=catchup_uc,
        sync_repo=sync_repo,
        metrics_repo=metrics_repo,
        local_tz=TZ_AR,
        sync_agent=sync_agent,
        app_config_repo=app_config_repo,
        update_check_trigger=update_check_trigger,
    )

    # ── Daemon de captura del sensor WH1081 ──────────────────────────────
    # Se construye ANTES de MainApplication para poder pasar sensor_status_fn.
    _sensor_stop = threading.Event()
    _collector: SensorCollectorDaemon | None = None
    try:
        _capture_uc = CaptureLiveReadingUseCase(
            sensor_source=PywwsLiveSource(),
            sensor_repo=sensor_repo,
            sync_repo=sync_repo,
            station_uuid=_station_uuid,
            parser=_parser,
            time_provider=clock,
        )
        _collector = SensorCollectorDaemon(
            factory=factory,
            use_case=_capture_uc,
            stop_event=_sensor_stop,
        )
        _collector.start()
        print("[sensor] Daemon de captura iniciado")
    except Exception as _exc:
        print(f"[sensor] Daemon no iniciado (sin sensor o pywws no instalado): {_exc}")

    # Callable que MainApplication consulta cada 15s para el indicador del
    # header. Captura snapshot del ref para que la closure sea estable.
    _captured_collector = _collector

    def _sensor_status_fn() -> tuple[str, str]:
        if _captured_collector is None:
            return "warning", "Sensor: pywws no disponible o USB sin driver"
        if _captured_collector.is_alive():
            return "ok", "Sensor: hilo activo · WH1081 detectado"
        return "error", "Sensor: hilo detenido (verificar USB)"

    help_dir = ROOT / "resources" / "help"
    help_repo = HelpRepository(help_dir=help_dir)

    query_sensor_aggregated_uc = QuerySensorAggregatedUseCase(factory)

    app = MainApplication(
        auth_controller=auth_controller,
        onboarding_use_case=onboarding_uc,
        users_admin_controller=users_controller,
        list_audit_logs_uc=list_logs_uc,
        update_retention_uc=update_retention_uc,
        retention_use_case=retention_uc,
        export_data_uc=export_data_uc,
        export_raw_uc=export_raw_uc,
        db_factory=factory,
        metrics_repo=metrics_repo,
        help_repository=help_repo,
        app_config_repo=app_config_repo,
        empirical_controller=empirical_controller,
        sensor_status_fn=_sensor_status_fn,
        sync_controller=sync_controller,
        query_sensor_aggregated_uc=query_sensor_aggregated_uc,
        iea_name=app_config_repo.get("school_name") or "IEA — sin configurar",
        iea_cue=app_config_repo.get("cue") or "",
        local_tz=TZ_AR,
    )

    # ── Arrancar daemons de sync y update checker ─────────────────────────
    if sync_agent is not None:
        try:
            sync_agent.start()
            print("[sync] SyncAgentDaemon iniciado")
        except Exception as _exc:
            print(f"[sync] SyncAgentDaemon no inició: {_exc}")
    else:
        print("[sync] SyncAgentDaemon NO inicializado (faltan credentials). UI sigue operativa.")

    if update_checker is not None:
        try:
            update_checker.start()
            print("[update] UpdateCheckerDaemon iniciado")
        except Exception as _exc:
            print(f"[update] UpdateCheckerDaemon no inició: {_exc}")

    print("Iniciando YVY...")
    print(f"  DB: {db_path}")
    print(f"  Usuario: {DEFAULT_USER}  /  Contraseña: {DEFAULT_PASS}")
    try:
        app.mainloop()
    finally:
        # Orden de shutdown: update_checker → sync_agent → sensor
        if update_checker is not None:
            try:
                update_checker.stop(timeout_s=5.0)
            except Exception as _exc:
                print(f"[update] Error deteniendo UpdateCheckerDaemon: {_exc}")
        if sync_agent is not None:
            try:
                sync_agent.stop(timeout_s=10.0)
                print("[sync] SyncAgentDaemon detenido")
            except Exception as _exc:
                print(f"[sync] Error deteniendo SyncAgentDaemon: {_exc}")
        _sensor_stop.set()
    return 0


# ─── Helpers de wiring del sync agent ────────────────────────────────────


def _load_sync_credentials(app_config_repo) -> dict | None:
    """Carga y valida credentials de sync. None si faltan o son inválidas.

    Retorna dict con: server_url, station_uuid, key_version, key_bytes, http_client.
    """
    server_url = app_config_repo.get("sync_server_url")
    if not server_url:
        print("[sync] sync_server_url no configurado en app_config. Agent deshabilitado.")
        return None

    if not STATION_CREDENTIALS_PATH.exists():
        print(f"[sync] {STATION_CREDENTIALS_PATH} no existe. Agent deshabilitado.")
        return None

    try:
        creds = json.loads(STATION_CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[sync] Error leyendo credentials: {exc}. Agent deshabilitado.")
        return None

    try:
        station_uuid = uuid.UUID(creds["station_uuid"])
        key_version = int(creds["key_version"])
        key_bytes = bytes.fromhex(creds["key_hmac_hex"])
    except (KeyError, ValueError, TypeError) as exc:
        print(f"[sync] Credentials JSON inválido ({type(exc).__name__}: {exc}). Agent deshabilitado.")
        return None

    if len(key_bytes) < 32:
        print(f"[sync] key_hmac_hex demasiado corto ({len(key_bytes)} bytes, esperado >= 32). Agent deshabilitado.")
        return None

    cfg_station = app_config_repo.get("station_uuid")
    if cfg_station and uuid.UUID(cfg_station) != station_uuid:
        print(
            f"[sync] station_uuid en credentials ({station_uuid}) NO coincide "
            f"con app_config ({cfg_station}). Agent deshabilitado por seguridad."
        )
        return None

    http_client = HttpClient(server_url=server_url, verify=True)
    return {
        "server_url": server_url,
        "station_uuid": station_uuid,
        "key_version": key_version,
        "key_bytes": key_bytes,
        "http_client": http_client,
    }


def _try_build_sync_agent(
    *,
    app_config_repo,
    sync_repo,
    sync_agent_state_repo,
    time_provider,
    http_client,
    station_uuid,
    key_version,
    key_bytes,
    update_check_trigger,
) -> SyncAgentDaemon | None:
    config = SyncAgentConfig()
    return SyncAgentDaemon(
        sync_repo=sync_repo,
        agent_state_repo=sync_agent_state_repo,
        http_client=http_client,
        time_provider=time_provider,
        station_uuid=station_uuid,
        key_version=key_version,
        key=key_bytes,
        config=config,
        update_check_trigger=update_check_trigger,
        app_config_repo=app_config_repo,
    )


def _try_build_update_checker(
    *,
    app_config_repo,
    http_client,
    station_uuid,
    key_version,
    key_bytes,
    trigger,
) -> UpdateCheckerDaemon:
    from yvy import __version__
    return UpdateCheckerDaemon(
        http_client=http_client,
        app_config_repo=app_config_repo,
        trigger=trigger,
        station_uuid=station_uuid,
        key_version=key_version,
        key=key_bytes,
        edge_version=__version__,
    )


if __name__ == "__main__":
    sys.exit(main())
