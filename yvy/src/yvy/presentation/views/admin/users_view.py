"""Pantalla Admin/Usuarios.

Layout:

    ┌────────────────────────────────────────────────────────────────┐
    │ Usuarios                            [☐ Mostrar inactivos] [+]  │
    │ Gestión de cuentas de la institución                           │
    ├────────────────────────────────────────────────────────────────┤
    │ Usuario  │ Nombre        │ Rol       │ Estado │ Export │ Login│
    ├────────────────────────────────────────────────────────────────┤
    │ director │ Juan Pérez    │ Superadmin│ Activo │  Sí    │ ...  │
    │ profe1   │ María Gómez   │ Profesor  │ Activo │  No    │ ...  │
    │ ...                                                             │
    └────────────────────────────────────────────────────────────────┘

    [Editar]  [Reset password]  [Desactivar/Reactivar]
              ↑ habilitados solo si hay fila seleccionada

Decisiones:
- Treeview con selección simple. Las acciones aplican al user seleccionado.
- "Mostrar inactivos" toggle. Default: solo activos.
- Crear usuario abre el form modal vacío. Editar abre el modal con
  el user pre-cargado.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from yvy.domain.auth.exceptions import AuthError
from yvy.domain.auth.models import User
from yvy.presentation.components.user_form_modal import UserFormModal
from yvy.presentation.controllers.users_admin_controller import UsersAdminController
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_H1,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)

logger = logging.getLogger(__name__)


_ROLE_DISPLAY = {
    "superadmin": "Superadmin",
    "admin": "Admin",
    "profesor": "Profesor",
    "alumno": "Alumno",
}


class UsersView(tk.Frame):
    """Pantalla de Admin/Usuarios."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: UsersAdminController,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._controller = controller

        self._tree: ttk.Treeview | None = None
        self._show_inactive_var = tk.BooleanVar(value=False)
        self._action_buttons: list[ttk.Button] = []

        # Mapping iid → User para resolver al seleccionar
        self._users_by_iid: dict[str, User] = {}

        self._build()
        self.refresh()

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # Header
        header = tk.Frame(container, bg=BG_CREAM)
        header.pack(fill="x", pady=(0, SPACE_LG))

        titles = tk.Frame(header, bg=BG_CREAM)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Usuarios", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="Gestión de cuentas de la institución",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Acciones header
        actions = tk.Frame(header, bg=BG_CREAM)
        actions.pack(side="right")

        ttk.Checkbutton(
            actions,
            text="Mostrar inactivos",
            variable=self._show_inactive_var,
            command=self.refresh,
        ).pack(side="left", padx=(0, SPACE_SM))

        ttk.Button(
            actions,
            text="+ Nuevo usuario",
            style="Primary.TButton",
            command=self._on_create_clicked,
        ).pack(side="left")

        # Card con tabla
        card = tk.Frame(
            container,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="both", expand=True, pady=(0, SPACE_LG))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        columns = ("username", "fullname", "role", "active", "export", "last_login")
        self._tree = ttk.Treeview(
            inner,
            columns=columns,
            show="headings",
            height=12,
        )
        self._tree.heading("username", text="Usuario")
        self._tree.heading("fullname", text="Nombre completo")
        self._tree.heading("role", text="Rol")
        self._tree.heading("active", text="Estado")
        self._tree.heading("export", text="Export raw")
        self._tree.heading("last_login", text="Último acceso")

        self._tree.column("username", width=120, anchor="w")
        self._tree.column("fullname", width=200, anchor="w")
        self._tree.column("role", width=100, anchor="w")
        self._tree.column("active", width=80, anchor="center")
        self._tree.column("export", width=90, anchor="center")
        self._tree.column("last_login", width=160, anchor="w")

        self._tree.tag_configure("inactive", foreground=TEXT_SECONDARY)
        self._tree.tag_configure("admin_row", font=FONT_BODY_BOLD)

        scrollbar = ttk.Scrollbar(
            inner, orient="vertical", command=self._tree.yview
        )
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _e: self._on_edit_clicked())

        # Botones acción (al pie del card)
        actions_card = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        actions_card.pack(fill="x")

        # Botones acción.
        # Limitación conocida: xvfb (CI/Linux headless) no renderiza el text
        # de ttk.Button con state="disabled" desde la inicialización.
        # Fix: creamos sin disabled y aplicamos disabled solo si no hay
        # selección. En Windows real este workaround no es necesario.
        edit_btn = ttk.Button(
            actions_card,
            text="Editar usuario",
            style="Secondary.TButton",
            command=self._on_edit_clicked,
        )
        edit_btn.pack(side="left", padx=(0, SPACE_SM))
        self._action_buttons.append(edit_btn)

        toggle_btn = ttk.Button(
            actions_card,
            text="Desactivar",
            style="Secondary.TButton",
            command=self._on_toggle_active_clicked,
        )
        toggle_btn.pack(side="left")
        self._action_buttons.append(toggle_btn)
        self._toggle_btn = toggle_btn

        # Habilitar/deshabilitar según selección
        self._update_action_buttons()

    # ─── Refresh ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self._tree is None:
            return

        for item in self._tree.get_children():
            self._tree.delete(item)
        self._users_by_iid.clear()

        if self._show_inactive_var.get():
            users = self._controller.list_all_users()
        else:
            users = self._controller.list_active_users()

        for u in users:
            self._insert_user_row(u)

        self._update_action_buttons()

    def _insert_user_row(self, user: User) -> None:
        assert self._tree is not None

        active_str = "Activo" if user.is_active else "Inactivo"
        export_str = "Sí" if user.can_export_raw else "—"
        last_login_str = "—"
        if user.last_login is not None:
            last_login_str = user.last_login.strftime("%d/%m/%Y %H:%M")

        tags = []
        if not user.is_active:
            tags.append("inactive")
        if user.is_admin:
            tags.append("admin_row")

        iid = self._tree.insert(
            "",
            "end",
            values=(
                user.username,
                user.full_name,
                _ROLE_DISPLAY.get(user.role.value, user.role.value),
                active_str,
                export_str,
                last_login_str,
            ),
            tags=tuple(tags),
        )
        self._users_by_iid[iid] = user

    # ─── Selección y acciones ───────────────────────────────────────────

    def _selected_user(self) -> User | None:
        if self._tree is None:
            return None
        sel = self._tree.selection()
        if not sel:
            return None
        return self._users_by_iid.get(sel[0])

    def _on_select(self, _event=None) -> None:  # type: ignore[no-untyped-def]
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        u = self._selected_user()
        if u is not None:
            for btn in self._action_buttons:
                btn.state(["!disabled"])
            self._toggle_btn.configure(
                text="Reactivar" if not u.is_active else "Desactivar"
            )
        else:
            for btn in self._action_buttons:
                btn.state(["disabled"])

    def _on_create_clicked(self) -> None:
        UserFormModal(
            self.winfo_toplevel(),
            controller=self._controller,
            on_saved=self.refresh,
            editing=None,
        )

    def _on_edit_clicked(self) -> None:
        u = self._selected_user()
        if u is None:
            return
        UserFormModal(
            self.winfo_toplevel(),
            controller=self._controller,
            on_saved=self.refresh,
            editing=u,
        )

    def _on_toggle_active_clicked(self) -> None:
        u = self._selected_user()
        if u is None or u.id is None:
            return

        new_active = not u.is_active
        verb = "reactivar" if new_active else "desactivar"
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Estás seguro de querer {verb} al usuario '{u.username}'?",
        ):
            return

        try:
            self._controller.set_user_active(u.id, new_active)
        except AuthError as exc:
            messagebox.showerror(f"No se pudo {verb} el usuario", str(exc))
            return

        self.refresh()
