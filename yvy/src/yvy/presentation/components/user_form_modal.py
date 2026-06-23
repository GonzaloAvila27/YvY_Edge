"""Modal Crear/Editar user.

Modos:
- "create": form vacío. Al guardar llama a controller.create_user().
- "edit": form pre-poblado con un user existente. Al guardar:
    - Si password cambió → controller.reset_password_for().
    - Toggle export, rol, full_name → controller (use cases no permiten
      editar full_name/rol directamente, así que en Fase 7 NO se puede
      editar esos campos vía UI; solo password reset y toggle export.
      Dejo nota para Fase 7.5 si hace falta).

Decisión: en modo edit, mostramos username y rol como solo-lectura
(grayed out). Cambiar rol requiere borrar y recrear (el use case
SetUserActive no toca rol). Esto refleja que rol es semi-inmutable
una vez creado: minimiza errores de "ascendí a alumno a admin sin
querer".
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from yvy.domain.auth.enums import Role
from yvy.domain.auth.exceptions import AuthError
from yvy.domain.auth.models import User
from yvy.presentation.controllers.users_admin_controller import UsersAdminController
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_H2,
    FONT_SMALL,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


_ROLE_LABELS = {
    Role.SUPERADMIN: "Superadmin",
    Role.ADMIN: "Admin",
    Role.PROFESOR: "Profesor",
    Role.ALUMNO: "Alumno",
}
_LABEL_TO_ROLE = {v: k for k, v in _ROLE_LABELS.items()}


class UserFormModal(tk.Toplevel):
    """Modal para crear o editar un user."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: UsersAdminController,
        on_saved: Callable[[], None],
        *,
        editing: User | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_saved = on_saved
        self._editing = editing
        self._mode = "edit" if editing else "create"

        title = "Editar usuario" if self._mode == "edit" else "Crear nuevo usuario"
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.configure(bg=BG_CARD)

        # Variables
        self._username_var = tk.StringVar(value=editing.username if editing else "")
        self._fullname_var = tk.StringVar(value=editing.full_name if editing else "")
        self._password_var = tk.StringVar()
        initial_role = (
            _ROLE_LABELS[editing.role] if editing else _ROLE_LABELS[Role.ALUMNO]
        )
        self._role_var = tk.StringVar(value=initial_role)
        self._can_export_var = tk.BooleanVar(
            value=editing.can_export_raw if editing else False
        )

        self._build()
        self.grab_set()
        self.focus_set()
        self._center_on_parent(parent)

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=PRIMARY, height=48)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=("Editar usuario" if self._mode == "edit" else "Crear nuevo usuario"),
            bg=PRIMARY,
            fg="#FFFFFF",
            font=FONT_BODY_BOLD,
            padx=SPACE_XL,
        ).pack(side="left", fill="y")

        # Body
        body = tk.Frame(self, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        body.pack(fill="both", expand=True)

        # Username (read-only en edit)
        self._field(body, "Usuario", self._username_var, width=30)
        if self._mode == "edit":
            # Disable
            for w in body.winfo_children():
                if isinstance(w, ttk.Entry):
                    w.configure(state="disabled")
                    break

        # Full name
        self._field(body, "Nombre completo", self._fullname_var, width=40)

        # Password
        pwd_label_text = (
            "Nueva contraseña (vacío = no cambiar)"
            if self._mode == "edit"
            else "Contraseña (mín. 8 caracteres)"
        )
        pwd_entry = self._field(
            body, pwd_label_text, self._password_var, width=30, show="•"
        )

        # El superadmin no se resetea desde la UI: solo por CLI (hero-rescue).
        if self._mode == "edit" and self._editing is not None and (
            self._editing.role == Role.SUPERADMIN
        ):
            pwd_entry.configure(state="disabled")
            tk.Label(
                body,
                text="(La contraseña del superadmin solo se resetea por CLI)",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w", pady=(2, 0))

        # Role
        tk.Label(
            body,
            text="Rol",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(SPACE_SM, 2))
        # En creación NO se ofrece Superadmin: es singleton, se crea solo en
        # el onboarding. Su recuperación posterior es por CLI (hero-rescue).
        if self._mode == "create":
            role_values = [
                lbl for role, lbl in _ROLE_LABELS.items() if role != Role.SUPERADMIN
            ]
        else:
            role_values = list(_ROLE_LABELS.values())
        role_combo = ttk.Combobox(
            body,
            textvariable=self._role_var,
            values=role_values,
            state="readonly" if self._mode == "create" else "disabled",
            width=28,
        )
        role_combo.pack(anchor="w", fill="x")

        if self._mode == "edit":
            tk.Label(
                body,
                text="(El rol no se puede modificar después de crear el usuario)",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w", pady=(2, 0))

        # can_export_raw checkbox
        export_check = ttk.Checkbutton(
            body,
            text="Permitir exportar datos crudos (solo para envío externo)",
            variable=self._can_export_var,
        )
        export_check.pack(anchor="w", pady=(SPACE_MD, 0))

        # Footer botones
        footer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_MD)
        footer.pack(fill="x", side="bottom")

        ttk.Button(
            footer, text="Cancelar", command=self._close,
            style="Secondary.TButton",
        ).pack(side="right", padx=(SPACE_SM, 0))
        ttk.Button(
            footer,
            text="Guardar",
            command=self._submit,
            style="Primary.TButton",
        ).pack(side="right")

    def _submit(self) -> None:
        username = self._username_var.get().strip()
        fullname = self._fullname_var.get().strip()
        password = self._password_var.get()
        role = _LABEL_TO_ROLE.get(self._role_var.get(), Role.ALUMNO)
        can_export = self._can_export_var.get()

        # Validación previa al use case
        if not fullname:
            messagebox.showerror("Datos incompletos", "El nombre completo es obligatorio.", parent=self)
            return

        if self._mode == "create":
            if not username or len(username) < 3:
                messagebox.showerror("Error", "El usuario debe tener al menos 3 caracteres.", parent=self)
                return
            if len(password) < 8:
                messagebox.showerror("Error", "La contraseña debe tener al menos 8 caracteres.", parent=self)
                return

            try:
                self._controller.create_user(
                    username=username,
                    full_name=fullname,
                    password=password,
                    role=role,
                    can_export_raw=can_export,
                )
            except AuthError as exc:
                messagebox.showerror("No se pudo crear el usuario", str(exc), parent=self)
                return
            except Exception as exc:
                logger.exception("Error inesperado creando user")
                messagebox.showerror("Error inesperado", f"{exc}", parent=self)
                return

            logger.info("User creado vía UI: %s", username)
            self._on_saved()
            self._close()
            return

        # Modo edit
        assert self._editing is not None
        target_id = self._editing.id
        assert target_id is not None

        # 1. Si pwd cambió, reset
        if password:
            if len(password) < 8:
                messagebox.showerror("Error", "La contraseña debe tener al menos 8 caracteres.", parent=self)
                return
            try:
                self._controller.reset_password_for(target_id, password)
            except AuthError as exc:
                messagebox.showerror("No se pudo cambiar la contraseña", str(exc), parent=self)
                return

        # 2. Si toggle export cambió
        if can_export != self._editing.can_export_raw:
            try:
                self._controller.toggle_export_raw(target_id, can_export)
            except (AuthError, ValueError) as exc:
                messagebox.showerror("No se pudo modificar el flag de export", str(exc), parent=self)
                return

        logger.info("User editado vía UI: %s", self._editing.username)
        self._on_saved()
        self._close()

    def _field(
        self,
        parent: tk.Misc,
        label: str,
        var: tk.StringVar,
        width: int = 30,
        show: str | None = None,
    ) -> ttk.Entry:
        tk.Label(
            parent,
            text=label,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(SPACE_SM, 2))
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.pack(anchor="w", fill="x")
        return entry

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            self.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            mw = self.winfo_reqwidth()
            mh = self.winfo_reqheight()
            x = max(0, px + (pw - mw) // 2)
            y = max(0, py + (ph - mh) // 2)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
