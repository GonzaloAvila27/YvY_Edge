"""Pantalla Admin/Configuración.

Form con valores actuales de retention + botón Guardar. Si el user
es superadmin, también botón "Forzar retention ahora" que dispara el
job en thread daemon.

Decisión cerrada: cambios se aplican al próximo tic automático del
job. Forzar retention requiere click explícito.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from yvy.application.use_cases.admin.update_retention_policy import (
    KEY_RAW_DAYS,
    KEY_SYNC_SENT_DAYS,
    UpdateRetentionPolicyUseCase,
)
from yvy.application.use_cases.retention.run_retention_job import (
    RunRetentionJobUseCase,
)
from yvy.domain.retention.models import RetentionPolicy
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class SettingsView(tk.Frame):
    """Vista de Configuración del sistema."""

    def __init__(
        self,
        parent: tk.Misc,
        update_use_case: UpdateRetentionPolicyUseCase,
        retention_use_case: RunRetentionJobUseCase | None = None,
        is_superadmin: bool = False,
        metrics_repo: object | None = None,
        help_repository: object | None = None,
        sync_controller: object | None = None,
        current_user_role: str = "alumno",
        current_user_id: int = 0,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._update_uc = update_use_case
        self._retention_uc = retention_use_case
        self._is_superadmin = is_superadmin
        self._metrics_repo = metrics_repo
        self._help_repository = help_repository
        self._sync_controller = sync_controller
        self._user_role = current_user_role.lower()
        self._user_id = current_user_id

        # Cargar valores actuales
        default = RetentionPolicy.default()
        current = default
        if metrics_repo is not None:
            try:
                current = RetentionPolicy.from_app_metrics(metrics_repo)
            except Exception:
                logger.exception("No se pudo leer policy actual; usando defaults")

        self._raw_var = tk.IntVar(value=current.raw_days)
        self._sync_var = tk.IntVar(value=current.sync_sent_days)
        self._status_label: tk.Label | None = None

        self._build()

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # Header
        ttk.Label(container, text="Configuración", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Política de retención de datos del nodo local",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, SPACE_LG))

        # Sección actualizaciones (admin/superadmin únicamente)
        if self._user_role in ("admin", "superadmin") and self._sync_controller is not None:
            self._build_updates_section(container)

        # Card de retention
        card = tk.Frame(
            container,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, SPACE_LG))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="x")

        tk.Label(
            inner,
            text="Retención de datos",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
        ).pack(anchor="w", pady=(0, SPACE_SM))

        tk.Label(
            inner,
            text=(
                "Define cuántos días se conservan las lecturas crudas y los "
                "registros de sincronización ya enviados. Las observaciones "
                "procesadas (sensor_data) NUNCA se borran automáticamente "
                "por gobernanza institucional."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            wraplength=720,
            justify="left",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Spinbox raw_days
        self._spin_field(
            inner,
            "Lecturas crudas (sensor_raw)",
            "Días que se conservan las lecturas crudas del sensor antes de purgarse.",
            self._raw_var,
            from_=7,
            to=90,
        )

        # Spinbox sync_sent_days
        self._spin_field(
            inner,
            "Registros de sincronización enviados",
            "Días que se conservan los registros marcados como 'enviados al server central'.",
            self._sync_var,
            from_=14,
            to=180,
        )

        # Nota sobre cuándo se aplican los cambios
        tk.Label(
            inner,
            text=(
                "ⓘ Los cambios se aplicarán automáticamente en la próxima "
                "ejecución del job de mantenimiento (próximo arranque del "
                "sistema o cada 24 horas)."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            wraplength=720,
            justify="left",
        ).pack(anchor="w", pady=(SPACE_MD, SPACE_LG))

        # Botón guardar
        save_row = tk.Frame(inner, bg=BG_CARD)
        save_row.pack(anchor="w", fill="x")

        save_btn = ttk.Button(
            save_row,
            text="Guardar configuración",
            style="Primary.TButton",
            command=self._on_save_clicked,
        )
        save_btn.pack(side="left")

        self._status_label = tk.Label(
            save_row,
            text="",
            bg=BG_CARD,
            fg=SUCCESS,
            font=FONT_SMALL,
        )
        self._status_label.pack(side="left", padx=(SPACE_MD, 0))

        # Sección "Forzar retention" (solo superadmin)
        if self._is_superadmin and self._retention_uc is not None:
            danger_card = tk.Frame(
                container,
                bg=BG_CARD,
                highlightbackground=DANGER,
                highlightthickness=1,
            )
            danger_card.pack(fill="x")

            danger_inner = tk.Frame(
                danger_card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL,
            )
            danger_inner.pack(fill="x")

            # Header con título + help button
            danger_header = tk.Frame(danger_inner, bg=BG_CARD)
            danger_header.pack(anchor="w", fill="x")

            tk.Label(
                danger_header,
                text="Forzar retención manual",
                bg=BG_CARD,
                fg=DANGER,
                font=FONT_BODY_BOLD,
            ).pack(side="left")

            # Help button (solo si hay repo)
            if self._help_repository is not None:
                from yvy.presentation.components.help_button import HelpButton
                HelpButton(
                    danger_header,
                    help_repository=self._help_repository,  # type: ignore[arg-type]
                    article_key="admin_retencion",
                    bg=BG_CARD,
                ).pack(side="left", padx=(SPACE_SM, 0))

            tk.Label(
                danger_inner,
                text=(
                    "Aplica la política de retención inmediatamente, "
                    "sin esperar al próximo tic automático. "
                    "Solo accesible para superadministradores. "
                    "Asegurate de haber guardado los cambios primero."
                ),
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
                wraplength=720,
                justify="left",
            ).pack(anchor="w", pady=(SPACE_SM, SPACE_LG))

            ttk.Button(
                danger_inner,
                text="Forzar retención ahora",
                style="Primary.TButton",
                command=self._on_force_retention_clicked,
            ).pack(anchor="w")

    def _spin_field(
        self,
        parent: tk.Misc,
        label: str,
        help_text: str,
        var: tk.IntVar,
        *,
        from_: int,
        to: int,
    ) -> None:
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=(0, SPACE_MD))

        tk.Label(
            row, text=label,
            bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_BODY_BOLD,
        ).pack(anchor="w")
        tk.Label(
            row, text=help_text,
            bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL,
            wraplength=720, justify="left",
        ).pack(anchor="w", pady=(2, SPACE_SM))

        spin_row = tk.Frame(row, bg=BG_CARD)
        spin_row.pack(anchor="w")

        spin = ttk.Spinbox(
            spin_row,
            from_=from_,
            to=to,
            textvariable=var,
            width=6,
        )
        spin.pack(side="left")
        tk.Label(
            spin_row, text=" días",
            bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL,
        ).pack(side="left")

    # ─── Handlers ───────────────────────────────────────────────────────

    def _on_save_clicked(self) -> None:
        try:
            raw = self._raw_var.get()
            sync = self._sync_var.get()
        except tk.TclError:
            messagebox.showerror("Error", "Los valores deben ser números enteros.")
            return

        try:
            self._update_uc.execute(raw_days=raw, sync_sent_days=sync)
        except ValueError as exc:
            messagebox.showerror("Configuración inválida", str(exc))
            return
        except Exception:
            logger.exception("Error guardando policy")
            messagebox.showerror("Error", "No se pudo guardar la configuración.")
            return

        if self._status_label is not None:
            self._status_label.configure(text="✓ Guardado")
            self.after(3000, lambda: self._status_label.configure(text="") if self._status_label else None)

    def _build_updates_section(self, container: tk.Frame) -> None:
        """C10: Sección 'Actualizaciones de software' en SettingsView."""
        card = tk.Frame(
            container,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(0, SPACE_LG))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="x")

        tk.Label(inner, text="Actualizaciones de software", bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_BODY_BOLD).pack(anchor="w", pady=(0, SPACE_SM))

        # Información de versión y update pendiente
        try:
            update_info = self._sync_controller.get_update_info()  # type: ignore[union-attr]
            current_ver = update_info.get("current_version", "—")
            pending = update_info.get("pending")
            is_downloaded = update_info.get("is_downloaded", False)
        except Exception:
            current_ver = "—"
            pending = None
            is_downloaded = False

        tk.Label(inner, text=f"Versión instalada: {current_ver}", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL).pack(anchor="w")

        if pending:
            to_ver = pending.get("edge_version", "—")
            status_text = "descargado — listo para instalar" if is_downloaded else "disponible — pendiente de descarga"
            tk.Label(
                inner,
                text=f"Update disponible: {to_ver} ({status_text})",
                bg=BG_CARD,
                fg=SUCCESS if is_downloaded else TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w", pady=(2, SPACE_SM))

            if is_downloaded:
                ttk.Button(
                    inner,
                    text=f"Instalar versión {to_ver}...",
                    style="Primary.TButton",
                    command=self._on_open_update_modal,
                ).pack(anchor="w", pady=(0, SPACE_SM))
        else:
            tk.Label(inner, text="No hay actualizaciones pendientes.", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL).pack(anchor="w", pady=(2, SPACE_SM))

        # Releases en disco
        try:
            releases = self._sync_controller.get_releases_on_disk()  # type: ignore[union-attr]
        except Exception:
            releases = []

        if releases:
            sep = tk.Frame(inner, bg=BORDER, height=1)
            sep.pack(fill="x", pady=SPACE_SM)
            tk.Label(inner, text="Releases en disco:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL).pack(anchor="w")
            for r in releases:
                states_str = " · ".join(r.get("states", [])) or "—"
                lbl_text = f"  {r['version']}   ({states_str})"
                tk.Label(inner, text=lbl_text, bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_SMALL).pack(anchor="w")

            sep2 = tk.Frame(inner, bg=BORDER, height=1)
            sep2.pack(fill="x", pady=SPACE_SM)

            btn_row = tk.Frame(inner, bg=BG_CARD)
            btn_row.pack(anchor="w")

            previous = next((r["version"] for r in releases if "previous" in r.get("states", [])), None)
            stable = next((r["version"] for r in releases if "stable" in r.get("states", [])), None)

            if previous:
                ttk.Button(
                    btn_row,
                    text=f"Volver a versión anterior ({previous})",
                    command=lambda v=previous: self._on_rollback(v, "rollback_to_previous"),
                ).pack(side="left", padx=(0, SPACE_SM))

            if stable and stable != previous:
                ttk.Button(
                    btn_row,
                    text=f"Volver a última estable ({stable})",
                    command=lambda v=stable: self._on_rollback(v, "rollback_to_stable"),
                ).pack(side="left", padx=(0, SPACE_SM))

            ttk.Button(
                btn_row,
                text="Marcar versión actual como estable",
                command=self._on_mark_stable,
            ).pack(side="left")

    def _on_open_update_modal(self) -> None:
        """Abre el modal de actualización desde Settings."""
        if self._sync_controller is None:
            return
        try:
            update_info = self._sync_controller.get_update_info()  # type: ignore[union-attr]
            releases = self._sync_controller.get_releases_on_disk()  # type: ignore[union-attr]
        except Exception:
            return
        releases_simple = [{"version": r["version"], "states": r.get("states", [])} for r in releases]

        def _prevalidate():
            return self._sync_controller.prevalidate_install()  # type: ignore[union-attr]

        def _on_confirmed() -> None:
            # Buscar la MainApplication parent para la pantalla de transición
            w = self.winfo_toplevel()
            if hasattr(w, "_show_install_transition"):
                w._show_install_transition()  # type: ignore[union-attr]

        from yvy.presentation.components.update_modal import UpdateModal
        UpdateModal(
            self,
            update_info=update_info,
            releases_on_disk=releases_simple,
            user_role=self._user_role,
            on_install_confirmed=_on_confirmed,
            prevalidate_fn=_prevalidate,
        )

    def _on_rollback(self, to_version: str, reason: str) -> None:
        if not messagebox.askyesno(
            "Confirmar rollback",
            f"¿Volver a la versión {to_version}?\n\n"
            "El sistema se detendrá y reiniciará en esa versión.\n"
            "Si esa versión tiene un schema de DB anterior, se restaurará\n"
            "el backup pre-update correspondiente (se pierden datos del período intermedio).",
            parent=self,
        ):
            return
        if self._sync_controller is None:
            return
        try:
            result = self._sync_controller.rollback(  # type: ignore[union-attr]
                to_version=to_version,
                reason=reason,
                user_id=self._user_id,
            )
            if result and result.ok:
                messagebox.showinfo("Rollback iniciado", f"Volviendo a versión {to_version}...", parent=self)
                w = self.winfo_toplevel()
                if hasattr(w, "_quit_for_install"):
                    w._quit_for_install()  # type: ignore[union-attr]
            else:
                reason_str = result.reason if result else "error desconocido"
                messagebox.showerror("Error", f"No se pudo hacer rollback: {reason_str}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _on_mark_stable(self) -> None:
        if self._sync_controller is None:
            return
        try:
            update_info = self._sync_controller.get_update_info()  # type: ignore[union-attr]
            current_ver = update_info.get("current_version", "")
        except Exception:
            current_ver = ""
        if not current_ver:
            return
        if not messagebox.askyesno(
            "Marcar como estable",
            f"¿Marcar la versión actual ({current_ver}) como estable?\n\n"
            "Esta versión se conservará aunque se instalen versiones más nuevas,\n"
            "y se usará como punto de rollback seguro.",
            parent=self,
        ):
            return
        ok = self._sync_controller.mark_stable(current_ver, self._user_id)  # type: ignore[union-attr]
        if ok:
            messagebox.showinfo("Listo", f"Versión {current_ver} marcada como estable.", parent=self)
        else:
            messagebox.showerror("Error", "No se pudo marcar la versión.", parent=self)

    def _on_force_retention_clicked(self) -> None:
        if self._retention_uc is None:
            return
        if not messagebox.askyesno(
            "Confirmar",
            "¿Forzar la ejecución del job de retención ahora?\n\n"
            "Esto aplicará la política actual y purgará datos antiguos "
            "según los días configurados. La operación NO es reversible.",
        ):
            return

        # Disparar en thread daemon para no bloquear UI
        def _run() -> None:
            try:
                assert self._retention_uc is not None
                result = self._retention_uc.execute(force=True)
                logger.info(
                    "Retention forzado: %d raw, %d sync",
                    result.raw_deleted,
                    result.sync_archived,
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Retención completada",
                    f"Lecturas crudas borradas: {result.raw_deleted}\n"
                    f"Registros sync archivados: {result.sync_archived}",
                ))
            except Exception as exc:
                logger.exception("Error en retention forzado")
                self.after(0, lambda: messagebox.showerror(
                    "Error", f"No se pudo ejecutar la retención: {exc}",
                ))

        threading.Thread(target=_run, name="retention-forced", daemon=True).start()
