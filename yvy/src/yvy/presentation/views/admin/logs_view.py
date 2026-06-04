"""Pantalla Admin/Logs.

Treeview con audit_logs filtrable. Filtros mínimos: tipo de evento.
Filtro por usuario queda como columna deshabilitada (decisión: futuro).
"""

from __future__ import annotations

import json
import logging
import tkinter as tk
from tkinter import ttk

from yvy.application.use_cases.admin.list_audit_logs import ListAuditLogsUseCase
from yvy.domain.auth.enums import AuditEventType
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY_BOLD,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


_EVENT_LABELS = {
    AuditEventType.LOGIN_SUCCESS: "Login exitoso",
    AuditEventType.LOGIN_FAILED: "Login fallido",
    AuditEventType.USER_CREATED: "Usuario creado",
    AuditEventType.USER_DEACTIVATED: "Usuario desactivado",
    AuditEventType.USER_REACTIVATED: "Usuario reactivado",
    AuditEventType.PASSWORD_CHANGED: "Contraseña modificada",
    AuditEventType.PASSWORD_RESET_CLI: "Reset por CLI",
    AuditEventType.EXPORT_RAW: "Export crudo",
    AuditEventType.EXPORT_DATA: "Export procesado",
    AuditEventType.ONBOARDING_COMPLETED: "Onboarding completado",
    AuditEventType.CAN_EXPORT_TOGGLED: "Permiso export modificado",
}
_LABEL_TO_EVENT = {v: k for k, v in _EVENT_LABELS.items()}
_ALL_LABEL = "(Todos los eventos)"


class LogsView(tk.Frame):
    """Vista Admin/Logs."""

    def __init__(
        self,
        parent: tk.Misc,
        use_case: ListAuditLogsUseCase,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._use_case = use_case
        self._tree: ttk.Treeview | None = None
        self._event_filter_var = tk.StringVar(value=_ALL_LABEL)
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
        ttk.Label(titles, text="Bitácora", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="Eventos críticos del sistema (logins, cambios de cuenta, exports)",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Filtros
        filters = tk.Frame(header, bg=BG_CREAM)
        filters.pack(side="right")

        tk.Label(
            filters,
            text="Tipo de evento:",
            bg=BG_CREAM,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        ).pack(side="left", padx=(0, SPACE_SM))

        event_combo = ttk.Combobox(
            filters,
            textvariable=self._event_filter_var,
            values=[_ALL_LABEL] + list(_EVENT_LABELS.values()),
            state="readonly",
            width=28,
        )
        event_combo.pack(side="left", padx=(0, SPACE_SM))
        event_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        # Nota sobre filtro por usuario (deshabilitado)
        tk.Label(
            filters,
            text="(filtro por usuario: próximamente)",
            bg=BG_CREAM,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        ).pack(side="left")

        # Card con tabla
        card = tk.Frame(
            container,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        columns = ("ts", "event", "user", "source", "detail")
        self._tree = ttk.Treeview(
            inner, columns=columns, show="headings", height=18,
        )
        self._tree.heading("ts", text="Fecha y hora")
        self._tree.heading("event", text="Evento")
        self._tree.heading("user", text="Usuario")
        self._tree.heading("source", text="Origen")
        self._tree.heading("detail", text="Detalle")

        self._tree.column("ts", width=160, anchor="w")
        self._tree.column("event", width=180, anchor="w")
        self._tree.column("user", width=130, anchor="w")
        self._tree.column("source", width=80, anchor="center")
        self._tree.column("detail", width=350, anchor="w")

        scrollbar = ttk.Scrollbar(inner, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def refresh(self) -> None:
        if self._tree is None:
            return

        for item in self._tree.get_children():
            self._tree.delete(item)

        # Resolver filtro de evento
        label = self._event_filter_var.get()
        event_filter = _LABEL_TO_EVENT.get(label) if label != _ALL_LABEL else None

        entries = self._use_case.execute(
            event_type=event_filter,
            limit=200,
        )

        for e in entries:
            ts_str = e.ts.strftime("%d/%m/%Y %H:%M:%S") if e.ts else "—"
            event_label = _EVENT_LABELS.get(e.event_type, e.event_type.value)
            user_str = e.username or "—"
            source_str = e.source.value
            detail_str = self._format_detail(e.event_type, e.metadata)

            self._tree.insert(
                "",
                "end",
                values=(ts_str, event_label, user_str, source_str, detail_str),
            )

    @staticmethod
    def _format_detail(event_type: AuditEventType, metadata: dict) -> str:
        """Resumen legible del metadata según el tipo de evento."""
        if not metadata:
            return ""

        if event_type == AuditEventType.LOGIN_FAILED:
            return f"Razón: {metadata.get('reason', '—')}"
        if event_type in (AuditEventType.USER_CREATED, AuditEventType.USER_DEACTIVATED, AuditEventType.USER_REACTIVATED):
            target = metadata.get("created_username") or metadata.get("target_username") or "—"
            return f"Usuario afectado: {target}"
        if event_type == AuditEventType.PASSWORD_CHANGED:
            target = metadata.get("target_username", "—")
            self_svc = metadata.get("self_service", False)
            kind = "propia" if self_svc else "por admin"
            return f"Cambio {kind} sobre '{target}'"
        if event_type == AuditEventType.PASSWORD_RESET_CLI:
            return "Reset emergencia desde línea de comandos"
        if event_type == AuditEventType.ONBOARDING_COMPLETED:
            school = metadata.get("school_name", "—")
            return f"Institución: {school}"
        if event_type in (AuditEventType.EXPORT_DATA, AuditEventType.EXPORT_RAW):
            rows = metadata.get("rows", "—")
            return f"Filas exportadas: {rows}"
        if event_type == AuditEventType.CAN_EXPORT_TOGGLED:
            target = metadata.get("target_username", "—")
            new_val = metadata.get("new_value", False)
            return f"'{target}' → {'permitido' if new_val else 'revocado'}"

        # Fallback: JSON corto
        try:
            return json.dumps(metadata, ensure_ascii=False)[:80]
        except Exception:
            return str(metadata)[:80]
