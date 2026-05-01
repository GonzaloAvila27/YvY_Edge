"""MainApplication — orquestador de la app Tkinter.

Estados:
    1. Login: muestra LoginView a pantalla completa.
    2. Main: muestra Header + Sidebar + Content frame con la view activa.

Navegación entre views (post-login) via `_navigate(key)`. Las views se
instancian on-demand y se cachean para no recrear cada vez.

Smoke test al final: bloque __main__ que arranca la app sin backend
real (datos mockeados de usuario/IEA).
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from datetime import tzinfo
from tkinter import ttk
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from yvy.presentation.components import Header, Sidebar, SidebarItem
from yvy.presentation.theme import (
    BG_CREAM,
    SPACE_2XL,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    apply_theme,
)
from yvy.presentation.views.dashboard_admin import DashboardAdminView
from yvy.presentation.views.login_view import LoginView
from yvy.presentation.views.sync_status_view import SyncStatusView

if TYPE_CHECKING:
    from yvy.presentation.controllers.sync_controller import SyncController

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MockUser:
    """Mock de User para smoke tests. El real viene en Fase 6."""

    username: str
    full_name: str
    role: str  # superadmin / admin / profesor / alumno
    iea_name: str
    iea_cue: str


# Items de sidebar — declarativo, fácil de extender en fases siguientes.
_SIDEBAR_ITEMS: list[SidebarItem] = [
    SidebarItem(key="inicio", label="Inicio", icon_char="⌂"),
    SidebarItem(key="formulario", label="Formulario", icon_char="📋"),
    SidebarItem(key="dashboard", label="Dashboard", icon_char="📊"),
    SidebarItem(key="sync", label="Sync", icon_char="↻"),
    SidebarItem(key="ayuda", label="Ayuda", icon_char="?"),
    SidebarItem(key="usuarios", label="Usuarios", icon_char="👥", admin_only=True),
    SidebarItem(key="logs", label="Logs", icon_char="📜", admin_only=True),
    SidebarItem(key="datos", label="Datos", icon_char="💾", admin_only=True),
]


class MainApplication(tk.Tk):
    """Ventana raíz de la aplicación YVY.

    Args:
        sync_controller: opcional. Si se provee, la view ``sync`` muestra
            el SyncStatusView funcional. Si es None, muestra placeholder.
        local_tz: zona horaria local para conversiones de timestamps en
            las views. Default America/Argentina/Cordoba.
    """

    def __init__(
        self,
        sync_controller: SyncController | None = None,
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
        self._local_tz = local_tz or ZoneInfo("America/Argentina/Cordoba")

        # Estado
        self._current_user: MockUser | None = None
        self._current_view_key: str | None = None
        self._view_cache: dict[str, tk.Frame] = {}

        # Frames de top-level (se intercambian según estado)
        self._login_view: LoginView | None = None
        self._main_frame: tk.Frame | None = None
        self._header: Header | None = None
        self._sidebar: Sidebar | None = None
        self._content: tk.Frame | None = None

        self.show_login()

    # ─── Estados de la app ───────────────────────────────────────────────

    def show_login(self) -> None:
        """Muestra la pantalla de login (limpiando estado main si existía)."""
        if self._main_frame is not None:
            self._main_frame.destroy()
            self._main_frame = None
            self._header = None
            self._sidebar = None
            self._content = None
            self._view_cache.clear()

        self._login_view = LoginView(self, on_login=self._handle_login)
        self._login_view.pack(fill="both", expand=True)

    def show_main(self, user: MockUser) -> None:
        """Muestra la app autenticada con header + sidebar + content."""
        self._current_user = user

        if self._login_view is not None:
            self._login_view.destroy()
            self._login_view = None

        self._main_frame = tk.Frame(self, bg=BG_CREAM)
        self._main_frame.pack(fill="both", expand=True)

        # Header arriba
        self._header = Header(
            self._main_frame,
            iea_name=user.iea_name,
            iea_cue=user.iea_cue,
            user_name=user.full_name,
            user_role=user.role,
            on_notifications_click=self._on_notifications,
            on_avatar_click=self._on_avatar,
            notifications_count=2,  # mock
        )
        self._header.pack(side="top", fill="x")

        # Body: sidebar + content
        body = tk.Frame(self._main_frame, bg=BG_CREAM)
        body.pack(fill="both", expand=True)

        is_admin = user.role.lower() in ("admin", "superadmin")
        self._sidebar = Sidebar(
            body,
            items=_SIDEBAR_ITEMS,
            on_select=self._navigate,
            is_admin=is_admin,
        )
        self._sidebar.pack(side="left", fill="y")

        self._content = tk.Frame(body, bg=BG_CREAM)
        self._content.pack(side="left", fill="both", expand=True)

        # Estados iniciales del header (mock: todo OK)
        self._header.set_sensor_status("ok", "Sensor: live · última lectura hace 1m")
        self._header.set_sync_status("ok", "Sync OK · 0 pendientes")
        self._header.set_ntp_status("ok", "NTP sincronizado")
        self._header.set_connectivity_status("ok", "Online")

        # Vista por defecto
        default_view = "dashboard"
        self._navigate(default_view)
        self._sidebar.set_active(default_view)

    # ─── Navegación ──────────────────────────────────────────────────────

    def _navigate(self, key: str) -> None:
        """Cambia la view activa en el content frame."""
        if self._content is None:
            logger.warning("_navigate llamado antes de show_main")
            return

        if self._current_view_key == key:
            return

        # Ocultar la view anterior
        for child in self._content.winfo_children():
            child.pack_forget()

        # Resolver la view (cacheada o nueva)
        view = self._view_cache.get(key)
        if view is None:
            view = self._build_view(key)
            self._view_cache[key] = view

        view.pack(fill="both", expand=True)
        self._current_view_key = key

        # Sincronizar el item activo del sidebar
        if self._sidebar is not None:
            self._sidebar.set_active(key)

        logger.info("Navegando a view: %s", key)

    def _build_view(self, key: str) -> tk.Frame:
        """Instancia la view correspondiente a la key. Stubs para no implementadas."""
        assert self._content is not None

        if key == "dashboard":
            return DashboardAdminView(self._content)

        if key == "sync" and self._sync_controller is not None:
            return SyncStatusView(
                self._content,
                controller=self._sync_controller,
                local_tz=self._local_tz,
            )

        # Stubs para las demás views (se implementan en fases siguientes)
        return _PlaceholderView(self._content, label=self._stub_label(key))

    @staticmethod
    def _stub_label(key: str) -> str:
        labels = {
            "inicio": "Inicio (Fase posterior)",
            "formulario": "Formulario de carga (Fase posterior)",
            "sync": "Sincronización (sync_controller no inyectado)",
            "ayuda": "Ayuda (Fase 8)",
            "usuarios": "Administración de usuarios (Fase 6)",
            "logs": "Logs del sistema (Fase 7)",
            "datos": "Gestión de datos (Fase 5/7)",
        }
        return labels.get(key, f"View '{key}' no implementada")

    # ─── Handlers ────────────────────────────────────────────────────────

    def _handle_login(self, username: str, password: str) -> None:
        """Stub de login. En Fase 6 se delega al use case real."""
        logger.info("Mock login: user=%s", username)
        # Mock de usuario admin para smoke
        user = MockUser(
            username=username or "jperez",
            full_name="Juan Pérez",
            role="admin",
            iea_name="IEA Nº10 — Posadas",
            iea_cue="540178700",
        )
        self.show_main(user)

    def _on_notifications(self) -> None:
        logger.info("Click en bell de notificaciones (handler stub)")

    def _on_avatar(self) -> None:
        logger.info("Click en avatar (handler stub — abrirá ProfileModal en Fase 6)")

    # ─── Helpers ─────────────────────────────────────────────────────────

    def _center_window(self) -> None:
        """Centra la ventana en la pantalla al iniciar."""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - WINDOW_DEFAULT_WIDTH) // 2
        y = (sh - WINDOW_DEFAULT_HEIGHT) // 2
        self.geometry(f"{WINDOW_DEFAULT_WIDTH}x{WINDOW_DEFAULT_HEIGHT}+{x}+{y}")


class _PlaceholderView(tk.Frame):
    """View vacía con un label central. Para keys no implementadas todavía."""

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


# ─── Entry point para smoke test ─────────────────────────────────────────


def main() -> None:
    """Smoke test: abre la app con datos mock."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        datefmt="%H:%M:%S",
    )
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()
