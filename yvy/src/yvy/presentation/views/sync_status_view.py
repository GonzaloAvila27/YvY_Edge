"""Pantalla de sincronización (Sync).

Layout según mockup pantalla 5 del spec v1, extendido en Fase 9.2 paso
6.5 con visibilidad del estado del SyncAgentDaemon.

    ┌─ Card grande ──────────────────────────┬─ Stats ────────────┐
    │ Estado de sincronización               │ Pendientes      0  │
    │   ✓ Todo sincronizado                  │ Enviados hoy   24  │
    │   Agent: ● healthy                     │ Total local   152  │
    │   Última sync: 24/06/2026 08:45        │ Errores         0  │
    │   Última recuperación: 28/04 15:30     │                    │
    │                                        │                    │
    │   [Sincronizar ahora]                  │                    │
    │   [Recuperar buffer histórico]         │                    │
    │   [Pausar agent]  (condicional)        │                    │
    └────────────────────────────────────────┴────────────────────┘

El botón "Sincronizar ahora" llama a ``controller.force_wakeup_agent()``.
Si el agent NO está inyectado (modo dev sin credentials), el botón
sigue funcional pero solo refresca la vista.

El botón "Pausar/Reanudar" se muestra solo cuando hay un agent
inyectado y cambia su texto/acción según el estado actual del agent.
Latched states bloquean ambas operaciones con mensaje explícito.
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime, tzinfo
from tkinter import messagebox, ttk

from yvy.domain.sync.agent_state import AgentState, SyncAgentState, is_latched
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
    SyncStatus.DUPLICATE: ("Duplicado", SUCCESS),
    SyncStatus.ERROR: ("Error", DANGER),
}

# Mapeo AgentState → (label visible, color del dot)
_AGENT_DISPLAY: dict[AgentState, tuple[str, str]] = {
    AgentState.HEALTHY: ("● healthy", SUCCESS),
    AgentState.DEGRADED: ("● degraded", WARNING),
    AgentState.DISCONNECTED: ("● disconnected", WARNING),
    AgentState.AUTH_ERROR_LATCHED: ("● auth error (latched)", DANGER),
    AgentState.CLOCK_ERROR_LATCHED: ("● clock error (latched)", DANGER),
    AgentState.PAUSED: ("⏸ paused", TEXT_SECONDARY),
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
        self._agent_state_label: tk.Label | None = None
        self._last_sync_label: tk.Label | None = None
        self._last_catchup_label: tk.Label | None = None
        self._kpi_pending_value: tk.Label | None = None
        self._kpi_today_value: tk.Label | None = None
        self._kpi_total_value: tk.Label | None = None
        self._kpi_errors_value: tk.Label | None = None
        self._events_tree: ttk.Treeview | None = None
        self._refresh_btn: ttk.Button | None = None
        # Botón pausar/reanudar (creado solo si hay agent)
        self._pause_resume_btn: ttk.Button | None = None

        # Sección actualizaciones
        self._upd_status_label: tk.Label | None = None
        self._upd_detail_label: tk.Label | None = None
        self._upd_check_btn: ttk.Button | None = None
        self._upd_download_btn: ttk.Button | None = None
        self._upd_progress_label: tk.Label | None = None

        self._build()
        self.refresh()

    # ─── Construcción ────────────────────────────────────────────────────

    def _build(self) -> None:
        # Scroll de página: en notebooks chicas el contenido (estado, KPIs,
        # eventos, updates) supera el alto disponible. El Treeview de eventos
        # conserva su propio scroll interno; el de página se opera con la barra
        # (no se bindea la rueda para no robársela al Treeview).
        page_canvas = tk.Canvas(self, bg=BG_CREAM, highlightthickness=0)
        page_scroll = ttk.Scrollbar(self, orient="vertical", command=page_canvas.yview)
        page_canvas.configure(yscrollcommand=page_scroll.set)
        page_scroll.pack(side="right", fill="y")
        page_canvas.pack(side="left", fill="both", expand=True)

        container = tk.Frame(page_canvas, bg=BG_CREAM)
        _win = page_canvas.create_window((0, 0), window=container, anchor="nw")
        page_canvas.bind("<Configure>", lambda e: page_canvas.itemconfig(_win, width=e.width))
        container.bind(
            "<Configure>",
            lambda _: page_canvas.configure(scrollregion=page_canvas.bbox("all")),
        )

        pad = tk.Frame(container, bg=BG_CREAM, padx=SPACE_XL, pady=SPACE_XL)
        pad.pack(fill="both", expand=True)
        container = pad

        # Header de la view
        header_row = tk.Frame(container, bg=BG_CREAM)
        header_row.pack(fill="x", pady=(0, SPACE_LG))

        titles = tk.Frame(header_row, bg=BG_CREAM)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Enlace", style="H1.TLabel").pack(anchor="w")
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

        # Card de actualizaciones de software (siempre visible)
        self._build_updates_card(container)

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
        summary_row.pack(anchor="w", pady=(0, SPACE_SM))

        self._status_summary_label = tk.Label(
            summary_row,
            text="…",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY_BOLD,
        )
        self._status_summary_label.pack(side="left")

        # Estado del agent
        self._agent_state_label = tk.Label(
            inner,
            text="Agent: —",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
        )
        self._agent_state_label.pack(anchor="w", pady=(0, SPACE_MD))

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

        # Botón Pausar/Reanudar — solo si hay agent inyectado
        if self._controller.has_sync_agent():
            self._pause_resume_btn = ttk.Button(
                inner,
                text="Pausar agent",
                style="Secondary.TButton",
                command=self._on_pause_resume_clicked,
            )
            self._pause_resume_btn.pack(fill="x", pady=(SPACE_SM, 0))

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

        self._kpi_pending_value = self._make_kpi_row(inner, "Pendientes", "0", DANGER)
        self._kpi_today_value = self._make_kpi_row(inner, "Enviados hoy", "0", SUCCESS)
        self._kpi_total_value = self._make_kpi_row(inner, "Total local", "0", TEXT_PRIMARY)
        self._kpi_errors_value = self._make_kpi_row(inner, "Errores", "0", DANGER)

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
        self._events_tree.tag_configure("status_pending", foreground=WARNING)
        self._events_tree.tag_configure("status_sent", foreground=SUCCESS)
        self._events_tree.tag_configure("status_error", foreground=DANGER)
        self._events_tree.tag_configure("status_sending", foreground=PRIMARY)
        self._events_tree.tag_configure("status_duplicate", foreground=SUCCESS)

        scrollbar = ttk.Scrollbar(inner, orient="vertical", command=self._events_tree.yview)
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

        self._refresh_updates_section()

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

        # Estado del agent
        if self._agent_state_label is not None:
            if data.agent_state is None:
                self._agent_state_label.configure(
                    text="Agent: no inicializado (sin credentials)",
                    fg=TEXT_SECONDARY,
                )
            else:
                label_text, label_color = _AGENT_DISPLAY.get(
                    data.agent_state.state,
                    (str(data.agent_state.state), TEXT_SECONDARY),
                )
                self._agent_state_label.configure(
                    text=f"Agent: {label_text}",
                    fg=label_color,
                )

        # Actualizar texto del botón Pausar/Reanudar según estado
        self._refresh_pause_resume_button(data.agent_state)

        # Timestamps
        last_sync_text = "Última sincronización: —"
        if data.sent_today_count > 0:
            last_sync_text = f"Sincronizaciones de hoy: {data.sent_today_count} eventos"
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

    def _refresh_pause_resume_button(self, agent_state: SyncAgentState | None) -> None:
        """Actualiza texto/estado del botón Pausar/Reanudar según el agent."""
        if self._pause_resume_btn is None:
            return
        if agent_state is None:
            self._pause_resume_btn.configure(state="disabled", text="Pausar agent")
            return
        if is_latched(agent_state.state):
            self._pause_resume_btn.configure(
                state="disabled",
                text="Latched — requiere reiniciar",
            )
            return
        if agent_state.state == AgentState.PAUSED:
            self._pause_resume_btn.configure(state="normal", text="Reanudar agent")
        else:
            self._pause_resume_btn.configure(state="normal", text="Pausar agent")

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
            status_label, _ = _STATUS_DISPLAY.get(job.status, (str(job.status), TEXT_SECONDARY))
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
            "empirical_observation": "Observación empírica",
            "empirical_event": "Evento empírico",
        }.get(str(entity_type), str(entity_type))

    # ─── Card de actualizaciones ──────────────────────────────────────────

    def _build_updates_card(self, parent: tk.Misc) -> None:
        """Card inferior: estado de actualizaciones de software."""
        card = tk.Frame(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(SPACE_LG, 0))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        inner.pack(fill="x")

        hdr = tk.Frame(inner, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, SPACE_SM))
        ttk.Label(hdr, text="Actualizaciones de software", style="CardH3.TLabel").pack(side="left")

        self._upd_status_label = tk.Label(
            inner, text="Verificando...", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY, anchor="w"
        )
        self._upd_status_label.pack(anchor="w")

        self._upd_detail_label = tk.Label(
            inner,
            text="",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
            wraplength=700,
            justify="left",
        )
        self._upd_detail_label.pack(anchor="w", pady=(SPACE_SM, SPACE_MD))

        self._upd_progress_label = tk.Label(
            inner, text="", bg=BG_CARD, fg=PRIMARY, font=FONT_SMALL, anchor="w"
        )
        self._upd_progress_label.pack(anchor="w", pady=(0, SPACE_SM))

        btn_row = tk.Frame(inner, bg=BG_CARD)
        btn_row.pack(anchor="w")

        self._upd_check_btn = ttk.Button(
            btn_row,
            text="Verificar ahora",
            style="Secondary.TButton",
            command=self._on_check_updates_clicked,
        )
        self._upd_check_btn.pack(side="left", padx=(0, SPACE_SM))

        self._upd_download_btn = ttk.Button(
            btn_row,
            text="Descargar actualización",
            style="Secondary.TButton",
            state="disabled",
            command=self._on_download_clicked,
        )
        self._upd_download_btn.pack(side="left", padx=(0, SPACE_SM))
        # La instalación se dispara desde la notificación (campana): path
        # certificado en el test OTA 1.5.x. Se retiró aquí un botón "Instalar"
        # placeholder que nunca se cableó (state=disabled sin command ni refresh).

    def _refresh_updates_section(self) -> None:
        """Actualiza los labels de la sección de actualizaciones."""
        if self._upd_status_label is None:
            return

        info = self._controller.get_update_info()
        has_checker = info["has_update_checker"]
        pending = info["pending"]
        current = info["current_version"]
        last_checked = info["last_checked_at"]
        is_downloaded = info.get("is_downloaded", False)
        downloaded_path = info.get("downloaded_path")
        download_running = self._controller.is_download_running()

        if self._upd_check_btn is not None:
            self._upd_check_btn.configure(
                state="normal" if (has_checker and not download_running) else "disabled"
            )

        # Botón descargar: habilitado solo cuando hay pending, no descargado, no corriendo
        if self._upd_download_btn is not None:
            can_download = (
                has_checker and pending is not None and not is_downloaded and not download_running
            )
            self._upd_download_btn.configure(
                state="normal" if can_download else "disabled",
                text="Descargar actualización" if not download_running else "Descargando…",
            )

        if not has_checker:
            self._upd_status_label.configure(text="Sync no configurado.", fg=TEXT_SECONDARY)
            if self._upd_detail_label is not None:
                self._upd_detail_label.configure(
                    text="Las actualizaciones no están disponibles hasta que se configuren las credenciales de YVY Core."
                )
            return

        # Timestamp de última verificación
        checked_str = ""
        if last_checked:
            try:
                from datetime import UTC
                from datetime import datetime as _dt

                checked_dt = _dt.fromisoformat(last_checked)
                mins_ago = int((_dt.now(UTC) - checked_dt.astimezone(UTC)).total_seconds() / 60)
                checked_str = f"Última verificación: hace {mins_ago} min"
            except Exception:
                checked_str = f"Última verificación: {last_checked[:19]}"

        if pending is None:
            self._upd_status_label.configure(text=f"Sistema al día (versión {current})", fg=SUCCESS)
            if self._upd_detail_label is not None:
                self._upd_detail_label.configure(text=checked_str)
        elif is_downloaded:
            version = pending.get("edge_version", "?")
            self._upd_status_label.configure(
                text=f"Update {version} descargado, listo para instalar.", fg=SUCCESS
            )
            detail = f"Ruta: {downloaded_path}"
            if checked_str:
                detail += f"   {checked_str}"
            if self._upd_detail_label is not None:
                self._upd_detail_label.configure(text=detail)
        else:
            size_mb = pending.get("package_size_bytes", 0) / 1_000_000
            notes = pending.get("notes", "")
            version = pending.get("edge_version", "?")
            released = (pending.get("released_at") or "")[:10]
            detail_parts = [f"Tamaño: {size_mb:.1f} MB", f"Publicada: {released}"]
            if notes:
                detail_parts.append(f"Notas: {notes}")
            if checked_str:
                detail_parts.append(checked_str)
            self._upd_status_label.configure(
                text=f"Actualización disponible: {version}", fg=WARNING
            )
            if self._upd_detail_label is not None:
                self._upd_detail_label.configure(text="   ".join(detail_parts))

    def _on_check_updates_clicked(self) -> None:
        """Dispara el daemon de update checker y refresca la sección en 5s."""
        if self._upd_status_label is not None:
            self._upd_status_label.configure(text="Verificando...", fg=TEXT_SECONDARY)
        if self._upd_detail_label is not None:
            self._upd_detail_label.configure(text="")
        self._controller.trigger_update_check()
        self.after(5000, self._refresh_updates_section)

    # ─── Handlers ────────────────────────────────────────────────────────

    def _on_sync_now_clicked(self) -> None:
        """Click en 'Sincronizar ahora' — despierta al agent del idle sleep."""
        logger.info("Click en 'Sincronizar ahora'")
        if self._controller.has_sync_agent():
            agent_state = self._controller.get_agent_state()
            if agent_state is not None and is_latched(agent_state.state):
                messagebox.showwarning(
                    "Agent bloqueado",
                    "El sync agent está en estado latched "
                    f"({agent_state.state.value}).\n\n"
                    "Resolver la causa y reiniciar la aplicación.",
                )
                return
            self._controller.force_wakeup_agent()
        # Siempre refrescar la view
        self.refresh()

    def _on_catchup_clicked(self) -> None:
        """Abre el CatchupModal."""
        logger.info("Click en 'Recuperar buffer histórico'")

        modal = CatchupModal(
            parent=self.winfo_toplevel(),
            controller=self._controller,
            local_tz=self._local_tz,
        )
        original_close = modal.close

        def _close_and_refresh() -> None:
            original_close()
            self.refresh()

        modal.close = _close_and_refresh  # type: ignore[method-assign]

    def _on_download_clicked(self) -> None:
        """Inicia la descarga del paquete en un thread; actualiza UI via after()."""
        if self._upd_download_btn is not None:
            self._upd_download_btn.configure(state="disabled", text="Descargando…")
        if self._upd_progress_label is not None:
            self._upd_progress_label.configure(text="Iniciando descarga…")

        def _progress(downloaded: int, total: int) -> None:
            pct = int(downloaded * 100 / total) if total > 0 else 0
            dl_mb = downloaded / 1_000_000
            tot_mb = total / 1_000_000
            text = f"Descargando… {pct}%  ({dl_mb:.1f} / {tot_mb:.1f} MB)"
            self.after(
                0,
                lambda t=text: (
                    self._upd_progress_label.configure(text=t)
                    if self._upd_progress_label is not None
                    else None
                ),
            )

        def _done(result: dict) -> None:
            def _update() -> None:
                if self._upd_progress_label is not None:
                    if result.get("ok"):
                        self._upd_progress_label.configure(
                            text="Descarga completada. Hash SHA-256 verificado.", fg=SUCCESS
                        )
                    else:
                        self._upd_progress_label.configure(
                            text=f"Error: {result.get('error', 'desconocido')}", fg=DANGER
                        )
                self._refresh_updates_section()

            self.after(0, _update)

        started = self._controller.start_update_download(
            progress_callback=_progress,
            done_callback=_done,
        )
        if not started:
            if self._upd_progress_label is not None:
                self._upd_progress_label.configure(
                    text="No se pudo iniciar: ya hay una descarga en curso o sync no configurado.",
                    fg=WARNING,
                )
            self._refresh_updates_section()

    def _on_pause_resume_clicked(self) -> None:
        """Toggle pausar/reanudar según estado actual."""
        agent_state = self._controller.get_agent_state()
        if agent_state is None:
            return
        if is_latched(agent_state.state):
            return  # botón debería estar deshabilitado

        if agent_state.state == AgentState.PAUSED:
            confirmed = messagebox.askyesno(
                "Reanudar agent",
                "¿Reanudar el sync agent y volver a procesar la cola?",
            )
            if confirmed:
                self._controller.resume_agent()
                logger.info("Agent reanudado por operador desde UI")
        else:
            confirmed = messagebox.askyesno(
                "Pausar agent",
                "¿Pausar el sync agent? Los datos se siguen "
                "encolando localmente pero no se envían al servidor "
                "hasta que se reanude.",
            )
            if confirmed:
                self._controller.pause_agent(reason="operator request from UI")
                logger.info("Agent pausado por operador desde UI")

        self.refresh()
