"""Dashboard del profesor/admin (placeholder de Fase 4).

Layout asimétrico jerárquico según spec v1:

    [Título "Dashboard"]                          [Filtro] [Exportar]
    [Subtítulo "Resumen de los últimos 7 días"]

    ┌──────────────────────────────────────┐  ┌─────────────────┐
    │                                      │  │ KPI Temperatura │
    │      Card grande:                    │  ├─────────────────┤
    │      Temperatura últimos 7 días      │  │ KPI Humedad     │
    │      (placeholder rectangular)       │  ├─────────────────┤
    │                                      │  │ KPI Presión     │
    │                                      │  ├─────────────────┤
    │                                      │  │ KPI Lluvia 24h  │
    └──────────────────────────────────────┘  └─────────────────┘

    Eventos recientes y alertas                          [Ver todos →]
    [● 23/4 06:12 · Helada detectada · revisar cultivos]
    [● 22/4 14:30 · Granizo (relato Juan Pérez) · severidad moderada]
    [● 22/4 08:15 · Lluvia intensa · 28mm en 2hs]

Datos hardcoded por ahora. La integración con use cases reales viene
en fases posteriores (cuando estén los use cases de query del dashboard).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from yvy.presentation.theme import (
    ACCENT_GOLD,
    ACCENT_OLIVE,
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_H1,
    FONT_KPI_VALUE,
    FONT_SMALL,
    FONT_TINY,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class DashboardAdminView(tk.Frame):
    """View del dashboard admin/profesor."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._build()

    def _build(self) -> None:
        # Padding general
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # ─── Header de la view ───────────────────────────────────────────

        header_row = tk.Frame(container, bg=BG_CREAM)
        header_row.pack(fill="x", pady=(0, SPACE_LG))

        # Título + subtítulo
        titles = tk.Frame(header_row, bg=BG_CREAM)
        titles.pack(side="left", fill="x", expand=True)

        ttk.Label(titles, text="Dashboard", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text="Resumen de los últimos 7 días",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        # Acciones derecha
        actions = tk.Frame(header_row, bg=BG_CREAM)
        actions.pack(side="right")

        period_combo = ttk.Combobox(
            actions,
            values=["Últimos 7 días", "Últimos 30 días", "Últimos 90 días"],
            state="readonly",
            width=18,
            font=FONT_BODY,
        )
        period_combo.set("Últimos 7 días")
        period_combo.pack(side="left", padx=(0, SPACE_SM))

        ttk.Button(
            actions,
            text="Exportar",
            style="Secondary.TButton",
        ).pack(side="left")

        # ─── Cuerpo: gráfico grande + columna KPIs ───────────────────────

        body = tk.Frame(container, bg=BG_CREAM)
        body.pack(fill="both", expand=True, pady=(0, SPACE_LG))

        # Gráfico izquierda
        chart_card = self._make_card(body)
        chart_card.pack(side="left", fill="both", expand=True, padx=(0, SPACE_LG))

        chart_inner = tk.Frame(chart_card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        chart_inner.pack(fill="both", expand=True)

        ttk.Label(
            chart_inner,
            text="Temperatura últimos 7 días",
            style="CardH3.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Placeholder del gráfico (rectángulo gris claro)
        placeholder = tk.Frame(chart_inner, bg="#F0EDE3", height=200)
        placeholder.pack(fill="both", expand=True)

        tk.Label(
            placeholder,
            text="(gráfico de temperatura — Fase posterior)",
            bg="#F0EDE3",
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        ).pack(expand=True)

        # KPIs derecha
        kpis = tk.Frame(body, bg=BG_CREAM, width=260)
        kpis.pack(side="right", fill="y")
        kpis.pack_propagate(False)

        self._make_kpi(kpis, "Temperatura promedio", "21.4", "°C", "+0.3 vs semana anterior", SUCCESS)
        self._make_kpi(kpis, "Humedad relativa", "68", "%", "-2 vs semana anterior", DANGER)
        self._make_kpi(kpis, "Presión atmosférica", "1013", "hPa", "Estable", TEXT_SECONDARY)
        self._make_kpi(kpis, "Lluvia 24h", "12.3", "mm", "Lluvia moderada", TEXT_SECONDARY)

        # ─── Eventos recientes ───────────────────────────────────────────

        events_card = self._make_card(container)
        events_card.pack(fill="x")

        events_inner = tk.Frame(events_card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        events_inner.pack(fill="x")

        ev_header = tk.Frame(events_inner, bg=BG_CARD)
        ev_header.pack(fill="x", pady=(0, SPACE_MD))

        ttk.Label(
            ev_header,
            text="Eventos recientes y alertas",
            style="CardH3.TLabel",
        ).pack(side="left")

        link = tk.Label(
            ev_header,
            text="Ver todos →",
            bg=BG_CARD,
            fg=PRIMARY,
            font=FONT_SMALL,
            cursor="hand2",
        )
        link.pack(side="right")

        events = [
            ("23/4 06:12", "Helada detectada", "Acción: revisar cultivos", DANGER),
            ("22/4 14:30", "Granizo (relato de Juan Pérez)", "Severidad: moderada", ACCENT_GOLD),
            ("22/4 08:15", "Lluvia intensa", "28mm en 2hs", SUCCESS),
        ]

        for ts, title, detail, dot_color in events:
            self._make_event_row(events_inner, ts, title, detail, dot_color)

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _make_card(parent: tk.Misc) -> tk.Frame:
        """Crea un Frame estilo card (fondo blanco + borde fino)."""
        return tk.Frame(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )

    def _make_kpi(
        self,
        parent: tk.Misc,
        label: str,
        value: str,
        unit: str,
        delta: str,
        delta_color: str,
    ) -> None:
        """KPI card con label arriba, valor grande, delta abajo."""
        card = self._make_card(parent)
        card.pack(fill="x", pady=(0, SPACE_SM))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
        inner.pack(fill="x")

        tk.Label(
            inner,
            text=label,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_TINY,
            anchor="w",
        ).pack(fill="x")

        value_row = tk.Frame(inner, bg=BG_CARD)
        value_row.pack(fill="x", pady=(2, 0))

        tk.Label(
            value_row,
            text=value,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_KPI_VALUE,
        ).pack(side="left")

        tk.Label(
            value_row,
            text=unit,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
        ).pack(side="left", padx=(SPACE_SM, 0), pady=(SPACE_MD, 0))

        tk.Label(
            inner,
            text=delta,
            bg=BG_CARD,
            fg=delta_color,
            font=FONT_TINY,
            anchor="w",
        ).pack(fill="x")

    def _make_event_row(
        self,
        parent: tk.Misc,
        timestamp: str,
        title: str,
        detail: str,
        dot_color: str,
    ) -> None:
        """Fila de evento: punto de color + ts + título + detalle a la derecha."""
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=2)

        tk.Label(
            row,
            text="●",
            bg=BG_CARD,
            fg=dot_color,
            font=("DejaVu Sans", 12),
        ).pack(side="left", padx=(0, SPACE_SM))

        tk.Label(
            row,
            text=timestamp,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            width=12,
            anchor="w",
        ).pack(side="left")

        tk.Label(
            row,
            text=title,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
            anchor="w",
        ).pack(side="left", padx=(SPACE_SM, 0))

        tk.Label(
            row,
            text=detail,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            anchor="e",
        ).pack(side="right")
