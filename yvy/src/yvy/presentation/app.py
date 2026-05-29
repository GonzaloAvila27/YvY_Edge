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
from dataclasses import dataclass
from datetime import tzinfo
from tkinter import ttk
import uuid
from typing import TYPE_CHECKING
from uuid import uuid4
from zoneinfo import ZoneInfo

from yvy.domain.auth.enums import Role
from yvy.domain.auth.exceptions import (
    InvalidCredentialsError,
    UserInactiveError,
)
from yvy.domain.auth.models import User
from yvy.presentation.components import Header, Sidebar, SidebarItem
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    PRIMARY,
    SPACE_2XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
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
    from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
    from yvy.application.use_cases.admin.update_retention_policy import (
        UpdateRetentionPolicyUseCase,
    )
    from yvy.application.use_cases.auth.complete_onboarding import (
        CompleteOnboardingResult,
        CompleteOnboardingUseCase,
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

logger = logging.getLogger(__name__)


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
    SidebarItem(key="inicio", label="Inicio", icon_char="⌂"),
    SidebarItem(key="formulario", label="Formulario", icon_char="📋"),
    SidebarItem(key="dashboard", label="Dashboard", icon_char="📊"),
    SidebarItem(key="sync", label="Sync", icon_char="↻"),
    SidebarItem(key="ayuda", label="Ayuda", icon_char="?"),
    SidebarItem(key="usuarios", label="Usuarios", icon_char="👥", admin_only=True),
    SidebarItem(key="logs", label="Logs", icon_char="📜", admin_only=True),
    SidebarItem(key="datos", label="Datos", icon_char="💾", admin_only=True),
    SidebarItem(key="config", label="Configuración", icon_char="⚙", admin_only=True),
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
        db_factory: object | None = None,
        help_repository: HelpRepository | None = None,
        app_config_repo: AppConfigRepository | None = None,
        hardware_fingerprint: str | None = None,
        empirical_controller: EmpiricalController | None = None,
        iea_name: str = "IEA — sin configurar",
        iea_cue: str = "—",
        local_tz: tzinfo | None = None,
    ) -> None:
        super().__init__()

        self.title("YVY — Sistema meteorológico escolar")
        self.geometry(f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        apply_theme(self)
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
        self._db_factory = db_factory
        self._help_repository = help_repository
        self._app_config_repo = app_config_repo
        self._hardware_fingerprint = hardware_fingerprint
        self._empirical_controller = empirical_controller
        self._iea_name = iea_name
        self._iea_cue = iea_cue
        self._local_tz = local_tz or ZoneInfo("America/Argentina/Cordoba")

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
        if self._wizard_view is not None:
            self._wizard_view.destroy()
            self._wizard_view = None
        if self._main_frame is not None:
            self._main_frame.destroy()
            self._main_frame = None
            self._header = None
            self._sidebar = None
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
        assert self._onboarding_use_case is not None, (
            "show_onboarding requiere onboarding_use_case inyectado"
        )

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
            except Exception:
                pass

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
            notifications_count=0,
        )
        self._header.pack(side="top", fill="x")

        # Body: sidebar + content
        body = tk.Frame(self._main_frame, bg=BG_CREAM)
        body.pack(fill="both", expand=True)

        is_admin = self._user_is_admin(user)
        self._sidebar = Sidebar(
            body,
            items=_SIDEBAR_ITEMS,
            on_select=self._navigate,
            is_admin=is_admin,
        )
        self._sidebar.pack(side="left", fill="y")

        self._content = tk.Frame(body, bg=BG_CREAM)
        self._content.pack(side="left", fill="both", expand=True)

        # Estados iniciales del header (mock por ahora; real con sync_controller)
        self._header.set_sensor_status("ok", "Sensor: live")
        self._header.set_sync_status("ok", "Sync OK")
        self._header.set_ntp_status("ok", "NTP sincronizado")
        self._header.set_connectivity_status("ok", "Online")

        # Vista por defecto según rol
        default_view = "formulario" if user_role == "alumno" else "dashboard"
        self._navigate(default_view)
        self._sidebar.set_active(default_view)

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

    # ─── Navegación ─────────────────────────────────────────────────────

    def _navigate(self, key: str) -> None:
        if self._content is None:
            logger.warning("_navigate llamado antes de show_main")
            return
        if self._current_view_key == key:
            return

        for child in self._content.winfo_children():
            child.pack_forget()

        view = self._view_cache.get(key)
        if view is None:
            view = self._build_view(key)
            self._view_cache[key] = view

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
            return DashboardAdminView(self._content)

        if key == "dashboard":
            return DashboardAdminView(self._content)

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
            and self._db_factory is not None
        ):
            current_user = (
                self._auth_controller.current_user
                if self._auth_controller is not None
                else None
            )
            return DataView(
                self._content,
                factory=self._db_factory,  # type: ignore[arg-type]
                export_data_uc=self._export_data_uc,
                export_raw_uc=self._export_raw_uc,
                current_user=current_user if isinstance(current_user, User) else None,
            )

        if key == "formulario" and self._empirical_controller is not None:
            current_user = (
                self._auth_controller.current_user
                if self._auth_controller is not None
                else None
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
            # Solo superadmin puede forzar retention
            is_superadmin = False
            if (
                self._auth_controller is not None
                and self._auth_controller.current_user is not None
            ):
                u = self._auth_controller.current_user
                from yvy.domain.auth.enums import Role
                is_superadmin = u.role == Role.SUPERADMIN
            return SettingsView(
                self._content,
                update_use_case=self._update_retention_uc,
                retention_use_case=self._retention_use_case,
                is_superadmin=is_superadmin,
                metrics_repo=self._metrics_repo,
                help_repository=self._help_repository,
            )

        return _PlaceholderView(self._content, label=self._stub_label(key))

    @staticmethod
    def _stub_label(key: str) -> str:
        labels = {
            "inicio": "Inicio (Fase posterior)",
            "formulario": "Formulario de carga (Fase posterior)",
            "sync": "Sincronización (sync_controller no inyectado)",
            "ayuda": "Ayuda (Fase 8)",
            "usuarios": "Administración de usuarios (Fase 6 — pendiente)",
            "logs": "Logs del sistema (Fase 7)",
            "datos": "Gestión de datos (Fase 5/7)",
        }
        return labels.get(key, f"View '{key}' no implementada")

    def _show_empirical_wizard(self) -> None:
        """Reemplaza el área de contenido con el wizard de carga empírica."""
        if self._content is None or self._empirical_controller is None:
            return
        current_user = (
            self._auth_controller.current_user
            if self._auth_controller is not None
            else None
        )
        if not isinstance(current_user, User):
            return
        for child in self._content.winfo_children():
            child.pack_forget()
        wizard = EmpiricalWizardView(
            self._content,
            controller=self._empirical_controller,
            current_user=current_user,
            on_complete=self._on_empirical_wizard_complete,
            on_cancel=lambda: self._navigate("formulario"),
        )
        wizard.pack(fill="both", expand=True)
        self._current_view_key = None
        if self._sidebar is not None:
            self._sidebar.set_active("formulario")

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
        logger.info("Click en bell de notificaciones (handler stub)")

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
        x = (sw - WINDOW_DEFAULT_WIDTH) // 2
        y = (sh - WINDOW_DEFAULT_HEIGHT) // 2
        self.geometry(f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}+{x}+{y}")


# ─── Modales auxiliares ─────────────────────────────────────────────────


class CloseInterceptModal(tk.Toplevel):
    """Modal que aparece al apretar X. NO permite cerrar la app."""

    def __init__(
        self,
        parent: tk.Tk,
        on_change_user,  # type: ignore[no-untyped-def]
        on_minimize,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent)
        self._on_change_user = on_change_user
        self._on_minimize = on_minimize

        self.title("¿Qué querés hacer?")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        # Header azul
        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="¿Qué querés hacer?",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        # Body
        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text=(
                "La aplicación funciona como servidor local. Los procesos "
                "de recolección y sincronización deben seguir activos."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Footer botones
        footer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_LG)
        footer.pack(fill="x", side="bottom")

        ttk.Button(
            footer,
            text="Cancelar",
            command=self._close,
            style="Secondary.TButton",
        ).pack(side="right", padx=(SPACE_SM, 0))

        ttk.Button(
            footer,
            text="Minimizar",
            command=self._do_minimize,
            style="Secondary.TButton",
        ).pack(side="right", padx=(SPACE_SM, 0))

        ttk.Button(
            footer,
            text="Cambiar usuario",
            command=self._do_change_user,
            style="Primary.TButton",
        ).pack(side="right")

        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

        # Centrar y bloquear interacción con la ventana padre
        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()
        self.focus_set()

    def _do_change_user(self) -> None:
        self._close()
        self._on_change_user()

    def _do_minimize(self) -> None:
        self._close()
        self._on_minimize()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            mw = self.winfo_reqwidth()
            mh = self.winfo_reqheight()
            x = max(0, px + (pw - mw) // 2)
            y = max(0, py + (ph - mh) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass


class UserMenuModal(tk.Toplevel):
    """Menú al click en avatar: cambiar usuario, ver perfil, etc."""

    def __init__(self, parent: tk.Tk, on_change_user) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_change_user = on_change_user

        self.title("Sesión")
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Sesión",
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Cambiar de usuario para iniciar sesión con otra cuenta.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        ttk.Button(
            body,
            text="Cambiar usuario",
            command=self._do_change_user,
            style="Primary.TButton",
        ).pack(fill="x")

        ttk.Button(
            body,
            text="Cerrar",
            command=self._close,
            style="Secondary.TButton",
        ).pack(fill="x", pady=(SPACE_SM, 0))

        self.bind("<Escape>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.update_idletasks()
        self._center_on_parent(parent)
        self.grab_set()
        self.focus_set()

    def _do_change_user(self) -> None:
        self._close()
        self._on_change_user()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            mw = self.winfo_reqwidth()
            mh = self.winfo_reqheight()
            x = max(0, px + (pw - mw) // 2)
            y = max(0, py + (ph - mh) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass


class _PlaceholderView(tk.Frame):
    def __init__(self, parent: tk.Misc, label: str) -> None:
        super().__init__(parent, bg=BG_CREAM)
        inner = tk.Frame(self, bg=BG_CREAM)
        inner.pack(expand=True)

        ttk.Label(inner, text=label, style="H1.TLabel").pack()
        ttk.Label(
            inner,
            text="Esta sección será implementada en una fase posterior.",
            style="Secondary.TLabel",
        ).pack(pady=(SPACE_2XL // 2, 0))


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
