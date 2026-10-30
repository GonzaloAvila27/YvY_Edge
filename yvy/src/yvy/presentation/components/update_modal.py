"""Modal de actualización de YVY Edge (C8).

Muestra el detalle técnico completo del update pendiente.
Solo admin/superadmin pueden confirmar la instalación.
Alumnos y profesores ven los detalles pero el botón está deshabilitado.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_TINY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_ADMIN_ROLES = {"admin", "superadmin"}


class UpdateModal(tk.Toplevel):
    """Modal con detalles del update pendiente.

    Args:
        parent: widget padre.
        update_info: dict con datos del update (de SyncController.get_update_info).
        releases_on_disk: lista de dicts {version, states} para la sección releases.
        user_role: rol del usuario actual.
        on_install_confirmed: callback cuando el admin confirma la instalación.
            Recibe el resultado de prevalidación como argumento.
        prevalidate_fn: callable() -> PrevalidationResult. Se llama al confirmar.
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        update_info: dict,
        releases_on_disk: list[dict],
        user_role: str,
        on_install_confirmed: Callable[[], None] | None = None,
        prevalidate_fn: Callable | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Actualización de YVY Edge")
        self.resizable(False, False)
        self.grab_set()

        self._update_info = update_info
        self._releases = releases_on_disk
        self._user_role = user_role.lower()
        self._on_confirm = on_install_confirmed
        self._prevalidate_fn = prevalidate_fn

        self._build()
        self.update_idletasks()
        self._center()

    # ─── Construcción ─────────────────────────────────────────────────────

    def _build(self) -> None:
        self.configure(bg=BG_CREAM)
        outer = tk.Frame(self, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_XL)
        outer.pack(fill="both", expand=True)

        # Título
        tk.Label(
            outer,
            text="Actualización de YVY Edge",
            bg=BG_CREAM,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
        ).pack(anchor="w", pady=(0, SPACE_SM))

        # Card de detalles
        card = tk.Frame(outer, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, SPACE_MD))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_LG)
        inner.pack(fill="x")

        info = self._update_info
        pending = info.get("pending", {}) or {}

        from_ver = info.get("current_version", "—")
        to_ver = pending.get("edge_version", "—")
        size_bytes = pending.get("package_size_bytes", 0)
        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
        released = pending.get("released_at", "—")
        sha = pending.get("package_sha256", "—")
        sha_short = sha[:16] + "..." if len(sha) > 16 else sha
        is_downloaded = info.get("is_downloaded", False)
        sha_status = "verificado ✓" if is_downloaded else "pendiente de descarga"
        notes = pending.get("notes", "")

        def _row(label: str, value: str, value_fg: str = TEXT_PRIMARY) -> None:
            row = tk.Frame(inner, bg=BG_CARD)
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=label,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
                width=28,
                anchor="w",
            ).pack(side="left")
            tk.Label(row, text=value, bg=BG_CARD, fg=value_fg, font=FONT_SMALL, anchor="w").pack(
                side="left"
            )

        _row("Versión actual:", from_ver)
        _row("Versión nueva:", to_ver, SUCCESS)
        _row("Tamaño:", f"{size_mb:.1f} MB" if size_mb else "—")
        _row("Publicada:", released)
        _row(
            "SHA-256:", f"{sha_short}  ({sha_status})", SUCCESS if is_downloaded else TEXT_SECONDARY
        )

        # Notas
        if notes:
            sep = tk.Frame(inner, bg=BORDER, height=1)
            sep.pack(fill="x", pady=(SPACE_SM, SPACE_SM))
            tk.Label(inner, text="Novedades:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL).pack(
                anchor="w"
            )
            tk.Label(
                inner,
                text=notes,
                bg=BG_CARD,
                fg=TEXT_PRIMARY,
                font=FONT_SMALL,
                wraplength=460,
                justify="left",
            ).pack(anchor="w", pady=(2, 0))

        # Advertencias del proceso
        sep2 = tk.Frame(inner, bg=BORDER, height=1)
        sep2.pack(fill="x", pady=SPACE_SM)
        for line in (
            "Al actualizar el sistema se detendrá 2-3 minutos.",
            "Se hará backup automático de la base de datos.",
            "Si algo falla, se vuelve a la versión anterior.",
            "No apagues la computadora durante el proceso.",
        ):
            tk.Label(
                inner, text=f"• {line}", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_TINY, anchor="w"
            ).pack(anchor="w")

        # Releases en disco
        if self._releases:
            sep3 = tk.Frame(inner, bg=BORDER, height=1)
            sep3.pack(fill="x", pady=SPACE_SM)
            releases_text = "  ·  ".join(
                f"{r['version']}{' (' + ', '.join(r['states']) + ')' if r['states'] else ''}"
                for r in self._releases
            )
            tk.Label(
                inner,
                text=f"Releases en disco: {releases_text}",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_TINY,
            ).pack(anchor="w")

        # Botones
        btn_row = tk.Frame(outer, bg=BG_CREAM)
        btn_row.pack(fill="x", pady=(SPACE_MD, 0))

        ttk.Button(btn_row, text="Cancelar", command=self.destroy).pack(side="left")

        can_install = self._user_role in _ADMIN_ROLES and is_downloaded

        install_btn = ttk.Button(
            btn_row,
            text="Actualizar ahora",
            style="Primary.TButton",
            command=self._on_install_clicked,
            state="normal" if can_install else "disabled",
        )
        install_btn.pack(side="right")

        if not is_downloaded:
            tk.Label(
                btn_row,
                text="Primero descargar el paquete (Enlace → Actualizaciones)",
                bg=BG_CREAM,
                fg=TEXT_SECONDARY,
                font=FONT_TINY,
            ).pack(side="right", padx=(0, SPACE_SM))
        elif self._user_role not in _ADMIN_ROLES:
            tk.Label(
                btn_row,
                text="Requiere permisos de administrador",
                bg=BG_CREAM,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(side="right", padx=(0, SPACE_SM))

    # ─── Handlers ─────────────────────────────────────────────────────────

    def _on_install_clicked(self) -> None:
        # 1. Pre-validar
        if self._prevalidate_fn is not None:
            try:
                result = self._prevalidate_fn()
                if not result.ok:
                    messagebox.showerror(
                        "No se puede instalar",
                        f"Pre-validación fallida:\n\n{result.reason}",
                        parent=self,
                    )
                    return
            except Exception as exc:
                messagebox.showerror("Error", f"Error al pre-validar: {exc}", parent=self)
                return

        # 2. Confirmación explícita
        confirmed = messagebox.askyesno(
            "Confirmar actualización",
            "¿Instalar ahora?\n\n"
            "El sistema se va a cerrar y reiniciar automáticamente.\n"
            "No apagues la computadora durante el proceso (2-3 minutos).",
            parent=self,
            icon="warning",
        )
        if not confirmed:
            return

        # 3. Pantalla de transición (C9.4): la maneja el llamador via callback
        self.destroy()
        if self._on_confirm:
            self._on_confirm()

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")
