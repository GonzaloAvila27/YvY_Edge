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
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._update_uc = update_use_case
        self._retention_uc = retention_use_case
        self._is_superadmin = is_superadmin
        self._metrics_repo = metrics_repo
        self._help_repository = help_repository

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
