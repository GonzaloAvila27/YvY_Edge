"""MainApplication — orquestador de la app Tkinter.

Estados:
    1. Login: muestra LoginView a pantalla completa.
    2. Main: muestra Header + Sidebar + Content frame con la view activa.

Comportamiento de cierre (Fase 6):
    La X (WM_DELETE_WINDOW) abre un modal con 3 opciones:
        - Cambiar usuario: vuelve al login screen sin matar workers.
        - Minimizar: ``iconify()`` la ventana.
        - Cancelar: descarta la acción.
    La app NO se cierra desde la UI. Se mata por proceso (Task Manager,
    pkill) o por apagado del SO. Esto garantiza que workers críticos
    (sync agent, retention) sigan vivos.

Autenticación:
    Si se inyecta ``auth_controller``, usa flujo real de auth con DB.
    Si es ``None``, usa stub con MockUser (compat con smoke pre-Fase-6).

Permisos:
    El sidebar muestra items admin solo si el user es admin/superadmin.
    Las views consultan ``Permissions`` para mostrar/ocultar acciones.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Final
from zoneinfo import ZoneInfo

from yvy.domain.auth.exceptions import (
    InvalidCredentialsError,
    UserInactiveError,
)
from yvy.domain.auth.models import User
from yvy.domain.sync.agent_state import AgentState, is_latched
from yvy.presentation.components import Header, Sidebar, SidebarItem
from yvy.presentation.components.close_intercept_modal import CloseInterceptModal
from yvy.presentation.components.pizarra_yvy import PizarraYvY
from yvy.presentation.components.placeholder_view import PlaceholderView
from yvy.presentation.components.user_menu_modal import UserMenuModal
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    SPACE_2XL,
    SPACE_MD,
    SPACE_SM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    apply_theme,
)
from yvy.presentation.views.admin.data_view import DataView
from yvy.presentation.views.admin.logs_view import LogsView
from yvy.presentation.views.admin.settings_view import SettingsView
from yvy.presentation.views.admin.users_view import UsersView
from yvy.presentation.views.dashboard_admin import DashboardAdminView
from yvy.presentation.views.empirical.detail_modal import EmpiricalDetailModal
from yvy.presentation.views.empirical.list_view import EmpiricalListView
from yvy.presentation.views.empirical.wizard_view import EmpiricalWizardView
from yvy.presentation.views.help_view import HelpView
from yvy.presentation.views.login_view import LoginView
from yvy.presentation.views.onboarding.wizard_view import OnboardingWizard
from yvy.presentation.views.sync_status_view import SyncStatusView

if TYPE_CHECKING:
    from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
    from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
    from yvy.application.use_cases.admin.import_data_csv import ImportDataCsvUseCase
    from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
    from yvy.application.use_cases.admin.update_retention_policy import (
        UpdateRetentionPolicyUseCase,
    )
    from yvy.application.use_cases.auth.complete_onboarding import (
        CompleteOnboardingResult,
        CompleteOnboardingUseCase,
    )
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.application.use_cases.retention.run_retention_job import (
        RunRetentionJobUseCase,
    )
    from yvy.infrastructure.help.help_repository import HelpRepository
    from yvy.infrastructure.persistence.app_config_repository import (
        AppConfigRepository,
    )
    from yvy.presentation.controllers.auth_controller import AuthController
    from yvy.presentation.controllers.empirical_controller import EmpiricalController
    from yvy.presentation.controllers.sync_controller import SyncController
    from yvy.presentation.controllers.users_admin_controller import (
        UsersAdminController,
    )

from yvy.presentation.controllers.catchup_controller import (
    CatchupController,
    LastObservationPort,
)
from yvy.presentation.controllers.sync_controller import SyncDashboardData
from yvy.presentation.controllers.update_flow_controller import (
    InstallResultMessage,
    UpdateFlowController,
)

logger = logging.getLogger(__name__)

_HEADER_POLL_MS: Final[int] = 15_000  # cada 15 segundos


# ─── Funciones de derivación de estado del header ───────────────────────────


def _derive_sync_status(data: SyncDashboardData) -> tuple[str, str]:
    """(state, tooltip) para el indicador Sync."""
    if data.agent_state is not None and is_latched(data.agent_state.state):
        return "error", f"Sync: agent bloqueado ({data.agent_state.state.value})"
    if data.error_count > 0:
        return "error", f"Sync: {data.error_count} errores en cola"
    if data.pending_count > 0:
        return "warning", f"Sync: {data.pending_count} pendientes"
    if data.agent_state is None:
        return "neutral", "Sync: sin agent (modo dev)"
    return "ok", f"Sync: al día · {data.sent_today_count} enviados hoy"


def _derive_ntp_status(data: SyncDashboardData) -> tuple[str, str]:
    """(state, tooltip) para el indicador NTP."""
    if data.agent_state is None:
        return "neutral", "NTP: sin datos (sin agent)"
    offset = data.agent_state.clock_offset_seconds
    sign = "+" if offset >= 0 else ""
    tip = f"NTP: desfase {sign}{offset:.1f}s"
    if abs(offset) < 5.0:
        return "ok", tip
    if abs(offset) < 60.0:
        return "warning", tip
    return "error", f"NTP: desfase crítico {sign}{offset:.1f}s"


def _derive_connectivity_status(data: SyncDashboardData) -> tuple[str, str]:
    """(state, tooltip) para el indicador de conectividad."""
    if data.agent_state is None:
        return "neutral", "Red: sin agent (modo dev)"
    state = data.agent_state.state
    if state == AgentState.HEALTHY:
        return "ok", "Online · servidor accesible"
    if state == AgentState.DEGRADED:
        return "warning", "Red: conexión degradada"
    if state == AgentState.DISCONNECTED:
        return "warning", "Desconectado del servidor"
    if state == AgentState.PAUSED:
        return "neutral", "Agent pausado por operador"
    if is_latched(state):
        return "error", f"Error de conexión: {state.value}"
    return "neutral", str(state)


@dataclass(frozen=True)
class MockUser:
    """Mock de User para smoke tests sin auth real.

    Cuando se inyecta ``auth_controller``, NO se usa este mock. Se usa
    el ``User`` real del dominio. ``MockUser`` queda solo para smoke
    tests y compatibilidad con código pre-Fase-6.
    """

    username: str
    full_name: str
    role: str
    iea_name: str
    iea_cue: str


_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem(key="inicio", label="Inicio", icon_name="inicio"),
    SidebarItem(key="formulario", label="Cuaderno", icon_name="Cuaderno"),
    SidebarItem(key="dashboard", label="Observatorio", icon_name="observatorio"),
    SidebarItem(key="sync", label="Enlace", icon_name="enlace", alumno_hidden=True),
    SidebarItem(key="ayuda", label="Pizarra", icon_name="pizarra"),
    SidebarItem(key="usuarios", label="Usuarios", icon_name="usuarios", admin_only=True),
    SidebarItem(key="logs", label="Bitácora", icon_name="bitacora", admin_only=True),
    SidebarItem(key="datos", label="Mediciones", icon_name="mediciones", admin_only=True),
    SidebarItem(key="config", label="Configuración", icon_name="configuracion", admin_only=True),
]


class MainApplication(tk.Tk):
    """Ventana raíz de la aplicación YVY.

    Args:
        sync_controller: opcional. Si se provee, view ``sync`` funcional.
        retention_use_case: opcional. Thread daemon al startup.
        auth_controller: opcional. Si se provee, login real con DB.
            Si None, usa stub con MockUser (smoke test).
        iea_name, iea_cue: identidad institucional. Mostrados en el
            header. Default placeholders.
        local_tz: zona horaria local. Default America/Argentina/Cordoba.
    """

    def __init__(
        self,
        sync_controller: SyncController | None = None,
        retention_use_case: RunRetentionJobUseCase | None = None,
        auth_controller: AuthController | None = None,
        onboarding_use_case: CompleteOnboardingUseCase | None = None,
        users_admin_controller: UsersAdminController | None = None,
        list_audit_logs_uc: ListAuditLogsUseCase | None = None,
        update_retention_uc: UpdateRetentionPolicyUseCase | None = None,
        metrics_repo: object | None = None,
        export_data_uc: ExportDataCsvUseCase | None = None,
        export_raw_uc: ExportRawCsvUseCase | None = None,
        import_data_uc: ImportDataCsvUseCase | None = None,
        db_factory: object | None = None,
        help_repository: HelpRepository | None = None,
        app_config_repo: AppConfigRepository | None = None,
        hardware_fingerprint: str | None = None,
        empirical_controller: EmpiricalController | None = None,
        sensor_history: LastObservationPort | None = None,
        sensor_status_fn: Callable[[], tuple[str, str]] | None = None,
        query_sensor_aggregated_uc: QuerySensorAggregatedUseCase | None = None,
        iea_name: str = "IEA — sin configurar",
        iea_cue: str = "—",
        local_tz: tzinfo | None = None,
    ) -> None:
        super().__init__()

        self.title("YVY Edge — Sistema meteorológico escolar")
        # Clampear al área usable: en netbooks escolares chicas (1366x768,
        # 1024x600) el alto por defecto (768) supera la pantalla y la ventana
        # queda más alta que el área visible → footer y bordes inferiores
        # cortados. min() no-opea en pantallas grandes.
        _sw, _sh = self.winfo_screenwidth(), self.winfo_screenheight()
        _margin = 72  # barra de tareas + barra de título
        _w = min(WINDOW_DEFAULT_WIDTH, _sw)
        _h = min(WINDOW_DEFAULT_HEIGHT, _sh - _margin)
        self.geometry(f"{_w}x{_h}")
        self.minsize(min(WINDOW_MIN_WIDTH, _sw), min(WINDOW_MIN_HEIGHT, _sh - _margin))

        from yvy.config.paths import RESOURCES_DIR

        _ico = RESOURCES_DIR / "yvy.ico"
        if _ico.exists():
            self.iconbitmap(str(_ico))

        # Cargar tema guardado ANTES de aplicar ttk styles
        from yvy.presentation.theme_manager import theme_manager, update_ttk_styles

        if app_config_repo is not None:
            try:
                from yvy.config.paths import DATA_DIR

                theme_manager.load(DATA_DIR)
            except Exception as exc:
                logger.warning("No se pudo cargar el tema guardado, se usa default: %s", exc)

        apply_theme(self)
        if theme_manager.mode == "dark":
            update_ttk_styles(self, theme_manager.palette)
        self._center_window()

        # Dependencias inyectadas
        self._sync_controller = sync_controller
        self._retention_use_case = retention_use_case
        self._auth_controller = auth_controller
        self._onboarding_use_case = onboarding_use_case
        self._users_admin_controller = users_admin_controller
        self._list_audit_logs_uc = list_audit_logs_uc
        self._update_retention_uc = update_retention_uc
        self._metrics_repo = metrics_repo
        self._export_data_uc = export_data_uc
        self._export_raw_uc = export_raw_uc
        self._import_data_uc = import_data_uc
        self._db_factory = db_factory
        self._help_repository = help_repository
        self._app_config_repo = app_config_repo
        self._hardware_fingerprint = hardware_fingerprint
        self._empirical_controller = empirical_controller
        self._sensor_status_fn = sensor_status_fn
        self._query_sensor_aggregated_uc = query_sensor_aggregated_uc

        # El flujo de update necesita el subsistema; sin él la campana no existe.
        self._update_flow: UpdateFlowController | None = (
            UpdateFlowController(
                updates=sync_controller,
                app_config=app_config_repo,
                schedule=lambda ms, fn: self.after(ms, fn),
            )
            if sync_controller is not None
            else None
        )

        # Use case de indicadores derivados (sin dependencia de DB propia)
        from yvy.application.use_cases.compute_derived import ComputeDerivedUseCase

        self._compute_derived_uc = (
            ComputeDerivedUseCase() if self._query_sensor_aggregated_uc is not None else None
        )
        self._header_poll_id: str | None = None
        self._empirical_wizard_active: bool = False  # bloquea navegación lateral
        self._iea_name = iea_name
        self._iea_cue = iea_cue
        self._local_tz = local_tz or ZoneInfo("America/Argentina/Cordoba")

        # El catchup necesita el sensor (para el modal) y la base (para el gap).
        self._catchup: CatchupController | None = (
            CatchupController(
                sensor_history=sensor_history,
                local_tz=self._local_tz,
                schedule=lambda ms, fn: self.after(ms, fn),
            )
            if sensor_history is not None and sync_controller is not None
            else None
        )

        # Estado de sesión
        self._current_user: User | MockUser | None = None
        self._current_view_key: str | None = None
        self._view_cache: dict[str, tk.Frame] = {}

        # Frames top-level
        self._login_view: LoginView | None = None
        self._wizard_view: OnboardingWizard | None = None
        self._main_frame: tk.Frame | None = None
        self._header: Header | None = None
        self._sidebar: Sidebar | None = None
        self._pizarra: PizarraYvY | None = None
        self._content: tk.Frame | None = None

        # Interceptar la X
        self.protocol("WM_DELETE_WINDOW", self._on_close_intercepted)

        # Disparar retention en background
        self._retention_thread: threading.Thread | None = None
        if self._retention_use_case is not None:
            self._start_retention_background()

        # Decisión: onboarding o login al startup
        if self._needs_onboarding():
            self.show_onboarding()
        else:
            self.show_login()

    def _needs_onboarding(self) -> bool:
        """True si hay onboarding_use_case + app_config_repo Y onboarding NO completado."""
        if self._onboarding_use_case is None or self._app_config_repo is None:
            return False
        return not self._app_config_repo.is_onboarding_completed()

    # ─── Background workers ─────────────────────────────────────────────

    def _start_retention_background(self) -> None:
        def _run() -> None:
            try:
                assert self._retention_use_case is not None
                result = self._retention_use_case.execute()
                if result.did_run:
                    logger.info(
                        "Retention background OK: %d raw, %d sync archivados",
                        result.raw_deleted,
                        result.sync_archived,
                    )
                else:
                    logger.debug(
                        "Retention background skipped: %s",
                        result.skipped_reason,
                    )
            except Exception:
                logger.exception("Retention background falló")

        thread = threading.Thread(
            target=_run,
            name="retention-startup",
            daemon=True,
        )
        self._retention_thread = thread
        thread.start()

    # ─── Estados ────────────────────────────────────────────────────────

    def show_login(self) -> None:
        """Pantalla de login. Limpia el main frame si existía."""
        self._cancel_header_polling()
        if self._wizard_view is not None:
            self._wizard_view.destroy()
            self._wizard_view = None
        if self._main_frame is not None:
            self._main_frame.destroy()
            self._main_frame = None
            self._header = None
            self._sidebar = None
            self._pizarra = None
            self._content = None
            self._view_cache.clear()
            self._current_view_key = None

        # Si había un user logueado, limpiarlo
        if self._auth_controller is not None:
            self._auth_controller.logout()
        self._current_user = None

        self._login_view = LoginView(self, on_login=self._handle_login)
        self._login_view.pack(fill="both", expand=True)

    def show_onboarding(self) -> None:
        """Wizard de onboarding (primera vez)."""
        assert (
            self._onboarding_use_case is not None
        ), "show_onboarding requiere onboarding_use_case inyectado"

        if self._login_view is not None:
            self._login_view.destroy()
            self._login_view = None

        self._wizard_view = OnboardingWizard(
            self,
            use_case=self._onboarding_use_case,
            on_complete=self._on_onboarding_complete,
            hardware_fingerprint=self._hardware_fingerprint,
        )
        self._wizard_view.pack(fill="both", expand=True)

    def _on_onboarding_complete(self, result: CompleteOnboardingResult) -> None:
        """Callback del wizard. Auto-login con el primer admin creado."""
        logger.info("Onboarding completado, auto-login del superadmin")

        if self._wizard_view is not None:
            self._wizard_view.destroy()
            self._wizard_view = None

        # Refrescar IEA name/cue desde app_config (el wizard los seteó)
        if self._app_config_repo is not None:
            name = self._app_config_repo.get("school_name")
            cue = self._app_config_repo.get("cue")
            if name:
                self._iea_name = name
            if cue:
                self._iea_cue = cue

        # Auto-login: el wizard NO nos da la password; necesitamos
        # buscar el user por id y hacer un login "trusted".
        # Decisión: como acabamos de crear al user con su password,
        # mostramos el LoginView pre-rellenando el username y dejamos
        # al user tipear la password. Más seguro que tener la password
        # en memoria del wizard hasta acá.
        self.show_login()
        if self._login_view is not None and hasattr(self._login_view, "set_username"):
            try:
                # Si LoginView soporta pre-fill, usarlo
                self._login_view.set_username(  # type: ignore[attr-defined]
                    self._auth_controller.current_user.username  # type: ignore[union-attr]
                    if self._auth_controller and self._auth_controller.current_user
                    else ""
                )
            except Exception as exc:
                logger.debug("Pre-fill de username en login falló (ignorado): %s", exc)

    def show_main(self, user: User | MockUser) -> None:
        """App autenticada con header + sidebar + content."""
        self._current_user = user

        if self._login_view is not None:
            self._login_view.destroy()
            self._login_view = None

        self._main_frame = tk.Frame(self, bg=BG_CREAM)
        self._main_frame.pack(fill="both", expand=True)

        # Datos para el header
        if isinstance(user, User):
            user_full_name = user.full_name
            user_role = user.role.value
        else:
            user_full_name = user.full_name
            user_role = user.role

        self._header = Header(
            self._main_frame,
            iea_name=self._get_iea_name(user),
            iea_cue=self._get_iea_cue(user),
            user_name=user_full_name,
            user_role=user_role,
            on_notifications_click=self._on_notifications,
            on_avatar_click=self._on_avatar_clicked,
            on_theme_toggle=self._toggle_theme,
            notifications_count=0,
        )
        self._header.pack(side="top", fill="x")

        # Body: sidebar + content
        body = tk.Frame(self._main_frame, bg=BG_CREAM)
        body.pack(fill="both", expand=True)

        is_admin = self._user_is_admin(user)
        is_alumno = self._user_is_alumno(user)
        self._sidebar = Sidebar(
            body,
            items=_SIDEBAR_ITEMS,
            on_select=self._navigate,
            is_admin=is_admin,
            is_alumno=is_alumno,
            on_toggle=self._on_sidebar_toggled,
        )
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.toggle()  # inicia siempre colapsado

        self._content = tk.Frame(body, bg=BG_CREAM)
        self._content.pack(side="left", fill="both", expand=True)

        # Pizarra YvY — panel lateral izquierdo, inicia oculta
        # Se empaqueta via before=self._content cuando se abre
        if self._help_repository is not None:
            self._pizarra = PizarraYvY(
                body,
                help_repository=self._help_repository,
                on_close=self._on_pizarra_closed,
                content_sibling=self._content,
            )

        # Arrancar polling de indicadores del header (actualiza cada 15s)
        self._start_header_polling()

        # Vista por defecto según rol
        default_view = "formulario" if user_role == "alumno" else "dashboard"
        self._navigate(default_view)
        self._sidebar.set_active(default_view)

        # Oferta de catchup al arranque
        if self._catchup is not None:
            self._catchup.schedule_startup_offer(
                ask=self._ask_catchup, open_modal=self._open_catchup_modal
            )

        # Resultado de update post-instalación (va antes que el catchup)
        if self._update_flow is not None:
            self._update_flow.schedule_install_result(self._present_install_result)

    # ─── Resultado de update post-instalación (C9) ──────────────────────

    def _present_install_result(self, message: InstallResultMessage) -> None:
        """Pinta el mensaje que decidió el controller. Acá no se decide nada."""
        from tkinter import messagebox

        show = messagebox.showinfo if message.severity == "info" else messagebox.showerror
        show(message.title, message.body, parent=self)

        if message.clear_update_alert and self._header is not None:
            self._header.set_update_alert(False)

    # ─── Catchup al arranque ─────────────────────────────────────────────

    def _ask_catchup(self, message: str) -> bool:
        from tkinter import messagebox

        return bool(messagebox.askyesno("Recuperar datos del sensor", message, parent=self))

    def _open_catchup_modal(self, since_utc: datetime) -> None:
        from yvy.presentation.components.catchup_modal import CatchupModal

        CatchupModal(
            parent=self,
            controller=self._sync_controller,
            local_tz=self._local_tz,
            auto_since=since_utc,
        )

    # ─── Polling de estado del header ───────────────────────────────────

    def _start_header_polling(self) -> None:
        """Cancela cualquier ciclo previo y dispara el primero inmediatamente."""
        self._cancel_header_polling()
        self._poll_header()

    def _cancel_header_polling(self) -> None:
        if self._header_poll_id is not None:
            try:
                self.after_cancel(self._header_poll_id)
            except Exception as exc:
                logger.debug("after_cancel de header polling falló (ignorado): %s", exc)
            self._header_poll_id = None

    def _poll_header(self) -> None:
        """Actualiza indicadores y reprograma el próximo tick."""
        if self._header is None:
            return
        self._update_header_status()
        self._header_poll_id = self.after(_HEADER_POLL_MS, self._poll_header)

    def _update_header_status(self) -> None:
        """Lee estado real de sensor + sync agent y lo refleja en el header."""
        if self._header is None:
            return

        # ── Sensor ──────────────────────────────────────────────────────
        if self._sensor_status_fn is not None:
            sensor_state, sensor_tip = self._sensor_status_fn()
        else:
            sensor_state, sensor_tip = "neutral", "Sensor: sin datos"
        self._header.set_sensor_status(sensor_state, sensor_tip)

        # ── Sync / NTP / Conectividad — requieren sync_controller ───────
        if self._sync_controller is None:
            self._header.set_sync_status("neutral", "Sync: sin controller")
            self._header.set_ntp_status("neutral", "NTP: sin datos")
            self._header.set_connectivity_status("neutral", "Red: sin datos")
            return

        try:
            data = self._sync_controller.get_dashboard_data(recent_limit=0)
        except Exception:
            logger.exception("Error en polling de indicadores del header")
            return

        sync_s, sync_t = _derive_sync_status(data)
        ntp_s, ntp_t = _derive_ntp_status(data)
        conn_s, conn_t = _derive_connectivity_status(data)

        self._header.set_sync_status(sync_s, sync_t)
        self._header.set_ntp_status(ntp_s, ntp_t)
        self._header.set_connectivity_status(conn_s, conn_t)

        # ── Alerta de update (campana roja parpadeante) ──────────────────
        if self._update_flow is None:
            return
        try:
            self._header.set_update_alert(self._update_flow.has_update_alert())
        except Exception as exc:
            logger.debug("No se pudo actualizar la alerta de update en header (ignorado): %s", exc)

    def _get_iea_name(self, user: User | MockUser) -> str:
        if isinstance(user, MockUser):
            return user.iea_name
        return self._iea_name

    def _get_iea_cue(self, user: User | MockUser) -> str:
        if isinstance(user, MockUser):
            return user.iea_cue
        return self._iea_cue

    @staticmethod
    def _user_is_admin(user: User | MockUser) -> bool:
        if isinstance(user, User):
            return user.is_admin
        return user.role.lower() in ("admin", "superadmin")

    @staticmethod
    def _user_is_alumno(user: User | MockUser) -> bool:
        if isinstance(user, User):
            from yvy.domain.auth.enums import Role

            return user.role == Role.ALUMNO
        return user.role.lower() == "alumno"

    # ─── Dark mode ──────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        """Cambia entre light/dark y propaga a todos los componentes."""
        from yvy.presentation.theme_manager import theme_manager, update_ttk_styles

        theme_manager.toggle()
        palette = theme_manager.palette
        update_ttk_styles(self, palette)
        self._propagate_theme(palette)

    def _propagate_theme(self, palette: dict) -> None:
        """Aplica la paleta a todos los componentes registrados."""
        # Fondo de la ventana raíz
        self.configure(bg=palette["bg"])
        if self._main_frame is not None:
            self._main_frame.configure(bg=palette["bg"])
        if self._content is not None:
            self._content.configure(bg=palette["bg"])
        if self._header is not None:
            self._header.apply_theme(palette)
        if self._sidebar is not None:
            self._sidebar.apply_theme(palette)
        if self._pizarra is not None:
            try:
                self._pizarra.apply_theme(palette)
            except Exception:
                logger.exception("apply_theme falló en PizarraYvY")
        # Propagar a todas las vistas cacheadas
        cached = set(self._view_cache.values())
        for view in cached:
            if hasattr(view, "apply_theme"):
                try:
                    view.apply_theme(palette)
                except Exception:
                    logger.exception("apply_theme falló en %s", type(view).__name__)
            else:
                # Best-effort para vistas sin apply_theme explícito
                try:
                    from yvy.presentation.theme_manager import recolor

                    recolor(view, palette)
                except Exception as exc:
                    logger.debug("recolor best-effort falló en vista (ignorado): %s", exc)
        # Propagar a vistas activas no cacheadas (ej. EmpiricalWizardView)
        if self._content is not None:
            from yvy.presentation.theme_manager import recolor

            for child in self._content.winfo_children():
                if child not in cached and hasattr(child, "apply_theme"):
                    try:
                        child.apply_theme(palette)
                    except Exception:
                        logger.exception("apply_theme falló en %s", type(child).__name__)

    # ─── Pizarra YvY ────────────────────────────────────────────────────

    def open_pizarra(self, article_key: str) -> None:
        """Abre la Pizarra YvY con el artículo dado. Coordina con menú lateral."""
        if self._pizarra is None:
            return
        # Si el sidebar está expandido, colapsarlo primero
        if self._sidebar is not None and not self._sidebar.is_collapsed:
            self._sidebar.toggle()
        self._pizarra.show(article_key)

    def _on_pizarra_closed(self) -> None:
        """Callback de cierre de la pizarra."""
        pass  # no-op; la pizarra ya se auto-ocultó via hide()

    def _on_sidebar_toggled(self) -> None:
        """Callback cuando el usuario usa el toggle del sidebar.

        Si el sidebar se acaba de expandir y la pizarra está abierta,
        cerrar la pizarra.
        """
        if self._pizarra is None or self._sidebar is None:
            return
        # toggle() ya cambió el estado: si ahora está expandido, cerrar pizarra
        if not self._sidebar.is_collapsed and self._pizarra.is_open():
            self._pizarra.hide()

    # ─── Navegación ─────────────────────────────────────────────────────

    def _navigate(self, key: str) -> None:
        if self._content is None:
            logger.warning("_navigate llamado antes de show_main")
            return
        if self._current_view_key == key:
            return

        # Bloquear navegación si hay un formulario empírico en progreso
        if self._empirical_wizard_active:
            if key == "formulario":
                # El wizard mismo navega de vuelta a "formulario" al cancelar/completar
                self._empirical_wizard_active = False
                if self._header is not None:
                    self._header.set_theme_toggle_enabled(True)
            else:
                from tkinter import messagebox

                salir = messagebox.askyesno(
                    "Carga en progreso",
                    "Hay una carga de formulario en progreso.\n\n"
                    "¿Cancelar la carga y salir de esta pantalla?",
                    default=messagebox.NO,
                    icon=messagebox.WARNING,
                )
                if not salir:
                    return
                self._empirical_wizard_active = False
                if self._header is not None:
                    self._header.set_theme_toggle_enabled(True)

        for child in self._content.winfo_children():
            child.pack_forget()

        view = self._view_cache.get(key)
        if view is None:
            view = self._build_view(key)
            self._view_cache[key] = view
            # Si la vista se construye después de un cambio de tema, aplicar paleta
            from yvy.presentation.theme_manager import recolor, theme_manager

            if theme_manager.mode == "dark":
                palette = theme_manager.palette
                if hasattr(view, "apply_theme"):
                    try:
                        view.apply_theme(palette)
                    except Exception as exc:
                        logger.debug("apply_theme en vista nueva falló (ignorado): %s", exc)
                else:
                    recolor(view, palette)

        view.pack(fill="both", expand=True)
        self._current_view_key = key

        if self._sidebar is not None:
            self._sidebar.set_active(key)

        logger.info("Navegando a view: %s", key)

    def _build_view(self, key: str) -> tk.Frame:
        assert self._content is not None

        if key == "inicio":
            # TODO Fase posterior: "Inicio" mostrará novedades, informes
            # del servidor central y curiosidades para alumnos (contenido
            # push desde yvy-server, motivacional/educativo). Por ahora
            # redirige al Dashboard mientras ese módulo no existe.
            return DashboardAdminView(
                self._content,
                db_factory=self._db_factory,
                local_tz=self._local_tz,
                query_sensor_aggregated_uc=self._query_sensor_aggregated_uc,
                current_user=self._current_user,
                station_uuid=self._app_config_repo.get("station_uuid")
                if self._app_config_repo is not None
                else None,
                compute_derived_uc=self._compute_derived_uc,
                help_repository=self._help_repository,
                open_pizarra=self.open_pizarra if self._pizarra is not None else None,
                export_data_uc=self._export_data_uc,
            )

        if key == "dashboard":
            return DashboardAdminView(
                self._content,
                db_factory=self._db_factory,
                local_tz=self._local_tz,
                query_sensor_aggregated_uc=self._query_sensor_aggregated_uc,
                current_user=self._current_user,
                station_uuid=self._app_config_repo.get("station_uuid")
                if self._app_config_repo is not None
                else None,
                compute_derived_uc=self._compute_derived_uc,
                help_repository=self._help_repository,
                open_pizarra=self.open_pizarra if self._pizarra is not None else None,
                export_data_uc=self._export_data_uc,
            )

        if key == "sync" and self._sync_controller is not None:
            return SyncStatusView(
                self._content,
                controller=self._sync_controller,
                local_tz=self._local_tz,
            )

        if key == "usuarios" and self._users_admin_controller is not None:
            return UsersView(
                self._content,
                controller=self._users_admin_controller,
            )

        if key == "logs" and self._list_audit_logs_uc is not None:
            return LogsView(
                self._content,
                use_case=self._list_audit_logs_uc,
            )

        if key == "ayuda" and self._help_repository is not None:
            return HelpView(
                self._content,
                help_repository=self._help_repository,
            )

        if (
            key == "datos"
            and self._export_data_uc is not None
            and self._export_raw_uc is not None
            and self._import_data_uc is not None
            and self._db_factory is not None
        ):
            current_user = (
                self._auth_controller.current_user if self._auth_controller is not None else None
            )
            return DataView(
                self._content,
                factory=self._db_factory,  # type: ignore[arg-type]
                export_data_uc=self._export_data_uc,
                export_raw_uc=self._export_raw_uc,
                import_data_uc=self._import_data_uc,
                current_user=current_user if isinstance(current_user, User) else None,
            )

        if key == "formulario" and self._empirical_controller is not None:
            current_user = (
                self._auth_controller.current_user if self._auth_controller is not None else None
            )
            if isinstance(current_user, User):
                return EmpiricalListView(
                    self._content,
                    controller=self._empirical_controller,
                    current_user=current_user,
                    on_open_wizard=self._show_empirical_wizard,
                    on_open_detail=self._open_empirical_detail,
                )

        if key == "config" and self._update_retention_uc is not None:
            is_superadmin = False
            user_role = "alumno"
            user_id = 0
            if self._auth_controller is not None and self._auth_controller.current_user is not None:
                u = self._auth_controller.current_user
                from yvy.domain.auth.enums import Role

                is_superadmin = u.role == Role.SUPERADMIN
                user_role = u.role.value
                user_id = u.id
            return SettingsView(
                self._content,
                update_use_case=self._update_retention_uc,
                retention_use_case=self._retention_use_case,
                is_superadmin=is_superadmin,
                metrics_repo=self._metrics_repo,
                help_repository=self._help_repository,
                sync_controller=self._sync_controller,
                current_user_role=user_role,
                current_user_id=user_id,
            )

        return PlaceholderView(self._content, label=self._stub_label(key))

    @staticmethod
    def _stub_label(key: str) -> str:
        labels = {
            "inicio": "Inicio (Fase posterior)",
            "formulario": "Cuaderno (Fase posterior)",
            "sync": "Enlace (sync_controller no inyectado)",
            "ayuda": "Pizarra (Fase 8)",
            "usuarios": "Administración de usuarios (Fase 6 — pendiente)",
            "logs": "Bitácora del sistema (Fase 7)",
            "datos": "Mediciones (Fase 5/7)",
        }
        return labels.get(key, f"View '{key}' no implementada")

    def _show_empirical_wizard(self) -> None:
        """Reemplaza el área de contenido con el wizard de carga empírica."""
        if self._content is None or self._empirical_controller is None:
            return
        current_user = (
            self._auth_controller.current_user if self._auth_controller is not None else None
        )
        if not isinstance(current_user, User):
            return
        for child in self._content.winfo_children():
            child.pack_forget()
        self._empirical_wizard_active = True
        if self._header is not None:
            self._header.set_theme_toggle_enabled(False)
        wizard = EmpiricalWizardView(
            self._content,
            controller=self._empirical_controller,
            current_user=current_user,
            on_complete=self._on_empirical_wizard_complete,
            on_cancel=lambda: self._navigate("formulario"),
            help_repository=self._help_repository,
            on_open_help=self.open_pizarra if self._pizarra is not None else None,
        )
        wizard.pack(fill="both", expand=True)
        self._current_view_key = None
        if self._sidebar is not None:
            self._sidebar.set_active("formulario")
        # Aplicar dark mode si está activo al momento de abrir el wizard
        from yvy.presentation.theme_manager import theme_manager

        if theme_manager.mode == "dark":
            wizard.apply_theme(theme_manager.palette)

    def _on_empirical_wizard_complete(self) -> None:
        self._navigate("formulario")
        list_view = self._view_cache.get("formulario")
        if isinstance(list_view, EmpiricalListView):
            list_view.refresh()

    def _open_empirical_detail(self, observation_id: uuid.UUID) -> None:
        if self._empirical_controller is None:
            return
        EmpiricalDetailModal(self, self._empirical_controller, observation_id)

    # ─── Handlers ───────────────────────────────────────────────────────

    def _handle_login(self, username: str, password: str) -> None:
        """Login real (vía AuthController) o mock si no hay controller."""
        if self._auth_controller is not None:
            try:
                user = self._auth_controller.login(username, password)
            except (InvalidCredentialsError, UserInactiveError) as exc:
                self._show_login_error(str(exc))
                return
            self.show_main(user)
            return

        # Modo mock (smoke sin auth)
        logger.info("Mock login: user=%s", username)
        mock = MockUser(
            username=username or "jperez",
            full_name="Juan Pérez",
            role="admin",
            iea_name=self._iea_name,
            iea_cue=self._iea_cue,
        )
        self.show_main(mock)

    def _show_login_error(self, message: str) -> None:
        """Muestra error de login al user (modal simple)."""
        if self._login_view is not None:
            # Delegamos al LoginView si tiene método; si no, modal genérico
            if hasattr(self._login_view, "show_error"):
                self._login_view.show_error(message)  # type: ignore[attr-defined]
                return

        # Fallback: modal simple
        from tkinter import messagebox

        messagebox.showerror("Error de inicio de sesión", message)

    def _on_notifications(self) -> None:
        """Abre el modal de actualización si hay un update descargado."""
        if self._update_flow is None:
            return

        user_role = "alumno"
        if self._current_user is not None:
            user_role = (
                self._current_user.role.value
                if isinstance(self._current_user, User)
                else self._current_user.role
            )

        params = self._update_flow.build_modal_params(user_role)
        if params is None:
            return

        from yvy.presentation.components.update_modal import UpdateModal

        UpdateModal(
            self,
            update_info=params.update_info,
            releases_on_disk=params.releases_on_disk,
            user_role=params.user_role,
            on_install_confirmed=self._show_install_transition,
            prevalidate_fn=self._update_flow.prevalidate_install,
        )

    def _show_install_transition(self) -> None:
        """C9.4: pantalla de transición antes de lanzar el instalador."""
        if self._update_flow is None:
            return
        user_id = 0
        if self._current_user is not None and hasattr(self._current_user, "id"):
            user_id = self._current_user.id or 0  # type: ignore[union-attr]

        # Mostrar overlay de transición
        overlay = tk.Toplevel(self)
        overlay.title("Instalando actualización...")
        overlay.resizable(False, False)
        overlay.grab_set()
        overlay.protocol("WM_DELETE_WINDOW", lambda: None)  # no cerrable

        frame = tk.Frame(overlay, bg=BG_CARD, padx=SPACE_2XL, pady=SPACE_2XL)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="Instalando actualización...",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
        ).pack(pady=(0, SPACE_MD))
        tk.Label(
            frame,
            text="El sistema se va a cerrar y reiniciar automáticamente.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
        ).pack()
        tk.Label(
            frame, text="NO apagues la computadora.", bg=BG_CARD, fg=DANGER, font=FONT_BODY_BOLD
        ).pack(pady=SPACE_SM)
        tk.Label(
            frame,
            text="Esto puede tomar 2-3 minutos.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
        ).pack()
        overlay.update_idletasks()
        # Centrar
        w, h = overlay.winfo_width(), overlay.winfo_height()
        overlay.geometry(
            f"+{(overlay.winfo_screenwidth()-w)//2}+{(overlay.winfo_screenheight()-h)//2}"
        )

        def _on_failure() -> None:
            overlay.destroy()
            from tkinter import messagebox

            messagebox.showerror("Error", "No se pudo iniciar la instalación.")

        self._update_flow.schedule_install(
            user_id=user_id,
            on_done=self._quit_for_install,
            on_failure=_on_failure,
        )

    def _quit_for_install(self) -> None:
        """Cierra la app para que INSTALL_UPDATE.bat tome el control."""
        logger.info("update.install.app_closing_for_install")
        self.quit()
        self.destroy()

    def _on_avatar_clicked(self) -> None:
        """Click en avatar: abre modal con opciones (cambiar usuario)."""
        UserMenuModal(self, on_change_user=self._handle_change_user)

    def _handle_change_user(self) -> None:
        """Vuelve al login screen. Workers siguen vivos."""
        logger.info("Cambio de usuario solicitado")
        self.show_login()

    # ─── Cierre interceptado ────────────────────────────────────────────

    def _on_close_intercepted(self) -> None:
        """WM_DELETE_WINDOW (X). Modal con opciones, NO cerrar la app."""
        CloseInterceptModal(
            self,
            on_change_user=self._handle_change_user,
            on_minimize=self._handle_minimize,
        )

    def _handle_minimize(self) -> None:
        try:
            self.iconify()
        except tk.TclError:
            logger.warning("No se pudo minimizar la ventana")

    # ─── Helpers ────────────────────────────────────────────────────────

    def _center_window(self) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        margin = 72  # barra de tareas + barra de título
        w = min(WINDOW_DEFAULT_WIDTH, sw)
        h = min(WINDOW_DEFAULT_HEIGHT, sh - margin)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - margin - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")


# ─── Entry point ────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        datefmt="%H:%M:%S",
    )
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()
