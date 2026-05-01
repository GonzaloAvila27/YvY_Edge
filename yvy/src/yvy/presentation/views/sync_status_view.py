"""Pantalla de sincronización (Sync).

Layout según mockup pantalla 5 del spec v1:

    ┌─ Card grande ──────────────────────────┬─ Stats ────────────┐
    │ Estado de sincronización               │ Pendientes      0  │
    │   ✓ Todo sincronizado                  │ Enviados hoy   24  │
    │   Última sync: 24/06/2026 08:45        │ Total local   152  │
    │   Última recuperación: 28/04 15:30     │ Errores         0  │
    │                                        │                    │
    │   [Sincronizar ahora]                  │                    │
    │   [Recuperar buffer histórico]         │                    │
    └────────────────────────────────────────┴────────────────────┘

    ┌─ Últimos eventos ──────────────────────────────────────────────┐
    │ Fecha       Hora    Evento                Detalle              │
    ├────────────────────────────────────────────────────────────────┤
    │ 24/04/2026  08:45   Sincronización compl. 24 registros enviados│
    │ ...                                                             │
    └────────────────────────────────────────────────────────────────┘

El botón "Sincronizar ahora" es stub (Fase 9 lo implementa con el sync
agent). El botón "Recuperar buffer histórico" abre CatchupModal.
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime, tzinfo
from tkinter import ttk

from yvy.domain.sync.enums import SyncStatus
from yvy.domain.sync.models import SyncJob
from yvy.presentation.components.catchup_modal import CatchupModal
from yvy.presentation.controllers.sync_controller import (
    SyncController,
    SyncDashboardData,
)
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    PRIMARY,
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


# Mapeo SyncStatus → (label visible, color del dot)
_STATUS_DISPLAY: dict[SyncStatus, tuple[str, str]] = {
    SyncStatus.PENDING: ("Pendiente", WARNING),
    SyncStatus.SENDING: ("Enviando", PRIMARY),
    SyncStatus.SENT: ("Enviado", SUCCESS),
    SyncStatus.ERROR: ("Error", DANGER),
}


class SyncStatusView(tk.Frame):
    """View de la pantalla de sincronización.

    Args:
        parent: widget padre (típicamente el content_frame de la app).
        controller: SyncController inyectado.
        local_tz: zona horaria local. Se pasa al CatchupModal.
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: SyncController,
        local_tz: tzinfo,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)

        self._controller = controller
        self._local_tz = local_tz

        # Refs a labels que se actualizan en refresh
        self._status_summary_label: tk.Label | None = None
        self._last_sync_label: tk.Label | None = None
        self._last_catchup_label: tk.Label | None = None
        self._kpi_pending_value: tk.Label | None = None
        self._kpi_today_value: tk.Label | None = None
        self._kpi_total_value: tk.Label | None = None
        self._kpi_errors_value: tk.Label | None = None
        self._events_tree: ttk.Treeview | None = None
        self._refresh_btn: ttk.Button | None = None

        self._build()
        self.refresh()

    # ─── Construcción ────────────────────────────────────────────────────

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # Header de la view
        header_row = tk.Frame(container, bg=BG_CREAM)
        header_row.pack(fill="x", pady=(0, SPACE_LG))

        titles = tk.Frame(header_row, bg=BG_CREAM)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Sincronización", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="Estado de la cola local y recuperación de buffer histórico",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(header_row, bg=BG_CREAM)
        actions.pack(side="right")
        self._refresh_btn = ttk.Button(
            actions,
            text="↻ Refrescar",
            style="Secondary.TButton",
            command=self.refresh,
        )
        self._refresh_btn.pack()

        # Banda superior: estado + KPIs lado a lado
        top_row = tk.Frame(container, bg=BG_CREAM)
        top_row.pack(fill="x", pady=(0, SPACE_LG))

        self._build_status_card(top_row)
        self._build_kpis_card(top_row)

        # Card inferior: tabla de eventos
        self._build_events_card(container)

    def _build_status_card(self, parent: tk.Misc) -> None:
        """Card grande izquierda con estado + botones de acción."""
        card = tk.Frame(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(side="left", fill="both", expand=True, padx=(0, SPACE_LG))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        ttk.Label(
            inner,
            text="Estado de sincronización",
            style="CardH3.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # Resumen visual (icono grande + texto)
        summary_row = tk.Frame(inner, bg=BG_CARD)
        summary_row.pack(anchor="w", pady=(0, SPACE_MD))

        self._status_summary_label = tk.Label(
            summary_row,
            text="…",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY_BOLD,
        )
        self._status_summary_label.pack(side="left")

        # Última sync
        self._last_sync_label = tk.Label(
            inner,
            text="Última sincronización: —",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
        )
        self._last_sync_label.pack(anchor="w")

        # Última recuperación de buffer
        self._last_catchup_label = tk.Label(
            inner,
            text="Última recuperación: —",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
        )
        self._last_catchup_label.pack(anchor="w", pady=(2, SPACE_LG))

        # Botones de acción
        ttk.Button(
            inner,
            text="Sincronizar ahora",
            style="Primary.TButton",
            command=self._on_sync_now_clicked,
        ).pack(fill="x", pady=(0, SPACE_SM))

        ttk.Button(
            inner,
            text="Recuperar buffer histórico",
            style="Secondary.TButton",
            command=self._on_catchup_clicked,
        ).pack(fill="x")

    def _build_kpis_card(self, parent: tk.Misc) -> None:
        """Card derecha con 4 KPIs verticales."""
        card = tk.Frame(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            width=240,
        )
        card.pack(side="right", fill="y")
        card.pack_propagate(False)

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        ttk.Label(
            inner,
            text="Estadísticas",
            style="CardH3.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_MD))

        self._kpi_pending_value = self._make_kpi_row(
            inner, "Pendientes", "0", DANGER
        )
        self._kpi_today_value = self._make_kpi_row(
            inner, "Enviados hoy", "0", SUCCESS
        )
        self._kpi_total_value = self._make_kpi_row(
            inner, "Total local", "0", TEXT_PRIMARY
        )
        self._kpi_errors_value = self._make_kpi_row(
            inner, "Errores", "0", DANGER
        )

    def _make_kpi_row(
        self,
        parent: tk.Misc,
        label: str,
        initial_value: str,
        value_color: str,
    ) -> tk.Label:
        """Fila label izq + valor der. Devuelve la ref del label de valor."""
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=SPACE_SM)

        tk.Label(
            row,
            text=label,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            anchor="w",
        ).pack(side="left")

        value_label = tk.Label(
            row,
            text=initial_value,
            bg=BG_CARD,
            fg=value_color,
            font=FONT_BODY_BOLD,
            anchor="e",
        )
        value_label.pack(side="right")
        return value_label

    def _build_events_card(self, parent: tk.Misc) -> None:
        """Card con Treeview de eventos."""
        card = tk.Frame(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        # Header
        header_row = tk.Frame(inner, bg=BG_CARD)
        header_row.pack(fill="x", pady=(0, SPACE_MD))
        ttk.Label(
            header_row,
            text="Últimos eventos",
            style="CardH3.TLabel",
        ).pack(side="left")

        # Treeview
        columns = ("date", "time", "status", "entity", "attempts")
        self._events_tree = ttk.Treeview(
            inner,
            columns=columns,
            show="headings",
            height=10,
        )
        self._events_tree.heading("date", text="Fecha")
        self._events_tree.heading("time", text="Hora")
        self._events_tree.heading("status", text="Estado")
        self._events_tree.heading("entity", text="Tipo")
        self._events_tree.heading("attempts", text="Intentos")

        self._events_tree.column("date", width=100, anchor="w")
        self._events_tree.column("time", width=80, anchor="w")
        self._events_tree.column("status", width=120, anchor="w")
        self._events_tree.column("entity", width=160, anchor="w")
        self._events_tree.column("attempts", width=80, anchor="center")

        # Tags para colorear filas según status
        self._events_tree.tag_configure(
            "status_pending", foreground=WARNING
        )
        self._events_tree.tag_configure(
            "status_sent", foreground=SUCCESS
        )
        self._events_tree.tag_configure(
            "status_error", foreground=DANGER
        )
        self._events_tree.tag_configure(
            "status_sending", foreground=PRIMARY
        )

        scrollbar = ttk.Scrollbar(
            inner, orient="vertical", command=self._events_tree.yview
        )
        self._events_tree.configure(yscrollcommand=scrollbar.set)

        self._events_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ─── API pública ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Pide datos al controller y actualiza todos los widgets."""
        try:
            data = self._controller.get_dashboard_data(recent_limit=50)
        except Exception:
            logger.exception("Error obteniendo datos para SyncStatusView")
            return

        self._apply_dashboard_data(data)

    # ─── Render ──────────────────────────────────────────────────────────

    def _apply_dashboard_data(self, data: SyncDashboardData) -> None:
        # Resumen visual de estado
        if data.is_catchup_running:
            text = "⟳ Recuperación en curso..."
            color = PRIMARY
        elif data.error_count > 0:
            text = f"⚠ {data.error_count} eventos con error"
            color = DANGER
        elif data.pending_count > 0:
            text = f"⏳ {data.pending_count} eventos pendientes"
            color = WARNING
        else:
            text = "✓ Todo sincronizado"
            color = SUCCESS

        if self._status_summary_label is not None:
            self._status_summary_label.configure(text=text, fg=color)

        # Timestamps
        last_sync_text = "Última sincronización: —"
        # Por ahora no tenemos métrica de last_successful_sync (Fase 9).
        # Aproximamos con sent_today_count > 0.
        if data.sent_today_count > 0:
            last_sync_text = (
                f"Sincronizaciones de hoy: {data.sent_today_count} eventos"
            )
        if self._last_sync_label is not None:
            self._last_sync_label.configure(text=last_sync_text)

        last_catchup_text = "Última recuperación: nunca"
        if data.last_catchup_at is not None:
            local_dt = data.last_catchup_at.astimezone(self._local_tz)
            last_catchup_text = (
                f"Última recuperación: {local_dt.strftime('%d/%m/%Y %H:%M')} "
                f"(total {data.catchup_runs_total})"
            )
        if self._last_catchup_label is not None:
            self._last_catchup_label.configure(text=last_catchup_text)

        # KPIs
        if self._kpi_pending_value is not None:
            self._kpi_pending_value.configure(
                text=str(data.pending_count + data.sending_count),
                fg=DANGER if data.pending_count > 0 else TEXT_PRIMARY,
            )
        if self._kpi_today_value is not None:
            self._kpi_today_value.configure(text=str(data.sent_today_count))
        if self._kpi_total_value is not None:
            self._kpi_total_value.configure(text=str(data.total_local_count))
        if self._kpi_errors_value is not None:
            self._kpi_errors_value.configure(
                text=str(data.error_count),
                fg=DANGER if data.error_count > 0 else TEXT_PRIMARY,
            )

        # Tabla de eventos
        self._populate_events(data.recent_events)

    def _populate_events(self, events: list[SyncJob]) -> None:
        if self._events_tree is None:
            return

        # Limpiar
        for item in self._events_tree.get_children():
            self._events_tree.delete(item)

        # Insertar
        for job in events:
            ts_local = self._format_local(job.created_at)
            date_str, time_str = ts_local
            status_label, _ = _STATUS_DISPLAY.get(
                job.status, (str(job.status), TEXT_SECONDARY)
            )
            entity_str = self._format_entity_type(job.entity_type)
            attempts_str = str(job.attempts)

            tag = f"status_{job.status.value}"
            self._events_tree.insert(
                "",
                "end",
                values=(date_str, time_str, status_label, entity_str, attempts_str),
                tags=(tag,),
            )

    def _format_local(self, dt: datetime | None) -> tuple[str, str]:
        if dt is None:
            return ("—", "—")
        local = dt.astimezone(self._local_tz)
        return (local.strftime("%d/%m/%Y"), local.strftime("%H:%M:%S"))

    @staticmethod
    def _format_entity_type(entity_type) -> str:  # type: ignore[no-untyped-def]
        return {
            "sensor_reading": "Lectura sensor",
            "empirical_record": "Registro empírico",
            "comment": "Comentario",
        }.get(str(entity_type), str(entity_type))

    # ─── Handlers ────────────────────────────────────────────────────────

    def _on_sync_now_clicked(self) -> None:
        """Stub. Fase 9 conecta con el sync agent."""
        logger.info("Click en 'Sincronizar ahora' (stub — Fase 9)")
        # Por ahora solo refrescar
        self.refresh()

    def _on_catchup_clicked(self) -> None:
        """Abre el CatchupModal."""
        logger.info("Click en 'Recuperar buffer histórico'")

        modal = CatchupModal(
            parent=self.winfo_toplevel(),
            controller=self._controller,
            local_tz=self._local_tz,
        )
        # Cuando se cierre, refrescar la view (los KPIs y eventos cambiaron)
        original_close = modal.close

        def _close_and_refresh() -> None:
            original_close()
            self.refresh()

        modal.close = _close_and_refresh  # type: ignore[method-assign]
