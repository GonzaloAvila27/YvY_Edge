"""Dashboard del profesor/admin.

Layout:
    [Título "Dashboard"]                          [Filtro] [Exportar]
    [Subtítulo "Resumen de los últimos 7 días"]

    ┌──────────────────────────────────────┐  ┌─────────────────┐
    │  Gráfico Temp °C / Humedad %         │  │ KPI Temperatura │
    │  matplotlib — 7 días, promedios/hora │  ├─────────────────┤
    │  Eje Y izq: temperatura (°C)         │  │ KPI Humedad     │
    │  Eje Y der: humedad (%)              │  ├─────────────────┤
    │  Eje X: fecha/hora local             │  │ KPI Presión     │
    │                                      │  ├─────────────────┤
    └──────────────────────────────────────┘  │ KPI Lluvia 24h  │
                                              └─────────────────┘
    Observaciones empíricas recientes              [Ver todos →]
    [● 31/5 08:15  Helada detectada  detalle]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING

import tkinter as tk
from tkinter import ttk

from yvy.presentation.theme import (
    ACCENT_GOLD,
    BG_CARD,
    BG_CREAM,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_BODY_BOLD,
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
    WARNING,
)

if TYPE_CHECKING:
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)

_DAYS = 7
_NO_DATA = "—"
_NO_DATA_DELTA = "sin datos suficientes"


# ─── Datos del dashboard ─────────────────────────────────────────────────────


@dataclass
class _KpiData:
    avg_temp: float | None = None
    avg_hum: float | None = None
    avg_pressure: float | None = None
    last_rain_24h: float | None = None
    row_count: int = 0


@dataclass
class _ChartPoint:
    ts: datetime
    temp: float | None
    hum: float | None


@dataclass
class _EventRow:
    ts_label: str
    title: str
    detail: str
    dot_color: str = SUCCESS


@dataclass
class _DashboardData:
    kpi: _KpiData = field(default_factory=_KpiData)
    chart_points: list[_ChartPoint] = field(default_factory=list)
    events: list[_EventRow] = field(default_factory=list)


# ─── View ────────────────────────────────────────────────────────────────────


class DashboardAdminView(tk.Frame):
    """Dashboard con KPIs y gráfico en vivo desde sensor_data."""

    def __init__(
        self,
        parent: tk.Misc,
        db_factory: SQLiteConnectionFactory | None = None,
        local_tz: tzinfo | None = None,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._db_factory = db_factory
        self._local_tz = local_tz or UTC
        self._data = self._load_data()
        self._build()

    # ─── Carga de datos ──────────────────────────────────────────────────

    def _load_data(self) -> _DashboardData:
        if self._db_factory is None:
            return _DashboardData()
        try:
            conn = self._db_factory.get_connection()
            return _DashboardData(
                kpi=self._query_kpis(conn),
                chart_points=self._query_chart(conn),
                events=self._query_events(conn),
            )
        except Exception:
            logger.exception("Error cargando datos del dashboard")
            return _DashboardData()

    def _query_kpis(self, conn) -> _KpiData:  # type: ignore[no-untyped-def]
        since = (datetime.now(UTC) - timedelta(days=_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        row = conn.execute(
            """
            SELECT
                AVG(CASE WHEN temp_outdoor IS NOT NULL THEN temp_outdoor END) AS avg_temp,
                AVG(CASE WHEN hum_outdoor  IS NOT NULL THEN hum_outdoor  END) AS avg_hum,
                AVG(CASE WHEN pressure_rel IS NOT NULL THEN pressure_rel END) AS avg_pres,
                COUNT(*) AS row_count
            FROM sensor_data
            WHERE observed_at >= ? AND is_valid = 1
            """,
            (since,),
        ).fetchone()

        rain_row = conn.execute(
            """
            SELECT rain_24h FROM sensor_data
            WHERE rain_24h IS NOT NULL AND is_valid = 1
            ORDER BY observed_at DESC LIMIT 1
            """,
        ).fetchone()

        return _KpiData(
            avg_temp=float(row[0]) if row and row[0] is not None else None,
            avg_hum=float(row[1]) if row and row[1] is not None else None,
            avg_pressure=float(row[2]) if row and row[2] is not None else None,
            last_rain_24h=float(rain_row[0]) if rain_row and rain_row[0] is not None else None,
            row_count=int(row[3]) if row else 0,
        )

    def _query_chart(self, conn) -> list[_ChartPoint]:  # type: ignore[no-untyped-def]
        """Promedios horarios de temperatura y humedad, últimos 7 días."""
        since = (datetime.now(UTC) - timedelta(days=_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        rows = conn.execute(
            """
            SELECT
                strftime('%Y-%m-%dT%H:00:00Z', observed_at) AS hour,
                AVG(temp_outdoor) AS temp,
                AVG(hum_outdoor)  AS hum
            FROM sensor_data
            WHERE observed_at >= ? AND is_valid = 1
            GROUP BY hour
            ORDER BY hour ASC
            """,
            (since,),
        ).fetchall()

        points = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(r[0].replace("Z", "+00:00"))
            except Exception:
                continue
            points.append(_ChartPoint(
                ts=ts,
                temp=float(r[1]) if r[1] is not None else None,
                hum=float(r[2]) if r[2] is not None else None,
            ))
        return points

    def _query_events(self, conn) -> list[_EventRow]:  # type: ignore[no-untyped-def]
        """Últimas observaciones empíricas de cualquier usuario."""
        try:
            rows = conn.execute(
                """
                SELECT eo.observed_at, eo.phenomenon_label, eo.place_description,
                       u.full_name
                  FROM empirical_observation eo
                  LEFT JOIN users u ON u.id = eo.observer_user_id
                 ORDER BY eo.observed_at DESC
                 LIMIT 5
                """
            ).fetchall()
        except Exception:
            return []

        events = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(
                    str(r[0]).replace("Z", "+00:00")
                ).astimezone(self._local_tz)
                ts_label = ts.strftime("%d/%m %H:%M")
            except Exception:
                ts_label = str(r[0])[:16] if r[0] else "—"

            title = str(r[1]) if r[1] else "Observación"
            detail = str(r[2]) if r[2] else ""
            observer = f" · {r[3]}" if r[3] else ""
            events.append(_EventRow(
                ts_label=ts_label,
                title=title,
                detail=detail + observer,
                dot_color=ACCENT_GOLD,
            ))
        return events

    # ─── Construcción de UI ───────────────────────────────────────────────

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        self._build_header(container)
        self._build_body(container)
        self._build_events(container)

    def _build_header(self, parent: tk.Misc) -> None:
        row = tk.Frame(parent, bg=BG_CREAM)
        row.pack(fill="x", pady=(0, SPACE_LG))

        titles = tk.Frame(row, bg=BG_CREAM)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Dashboard", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            titles,
            text=f"Resumen de los últimos {_DAYS} días",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(row, bg=BG_CREAM)
        actions.pack(side="right")
        combo = ttk.Combobox(
            actions,
            values=[f"Últimos {_DAYS} días"],
            state="readonly",
            width=18,
            font=FONT_BODY,
        )
        combo.set(f"Últimos {_DAYS} días")
        combo.pack(side="left", padx=(0, SPACE_SM))
        ttk.Button(actions, text="Exportar", style="Secondary.TButton").pack(side="left")

    def _build_body(self, parent: tk.Misc) -> None:
        body = tk.Frame(parent, bg=BG_CREAM)
        body.pack(fill="both", expand=True, pady=(0, SPACE_LG))

        # Gráfico izquierda
        chart_card = _make_card(body)
        chart_card.pack(side="left", fill="both", expand=True, padx=(0, SPACE_LG))
        self._build_chart_card(chart_card)

        # KPIs derecha
        kpis = tk.Frame(body, bg=BG_CREAM, width=260)
        kpis.pack(side="right", fill="y")
        kpis.pack_propagate(False)
        self._build_kpis(kpis)

    def _build_chart_card(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        ttk.Label(
            inner,
            text="Temperatura °C y Humedad % — últimos 7 días",
            style="CardH3.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_MD))

        pts = [p for p in self._data.chart_points
               if p.temp is not None or p.hum is not None]

        if not pts:
            no_data = tk.Frame(inner, bg="#F0EDE3")
            no_data.pack(fill="both", expand=True)
            tk.Label(
                no_data,
                text="Sin datos de sensor en los últimos 7 días",
                bg="#F0EDE3",
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(expand=True)
            return

        self._embed_chart(inner, pts)

    def _embed_chart(self, parent: tk.Misc, pts: list[_ChartPoint]) -> None:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.dates as mdates
        except ImportError:
            tk.Label(
                parent,
                text="matplotlib no disponible",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(expand=True)
            return

        temps = [p for p in pts if p.temp is not None]
        hums = [p for p in pts if p.hum is not None]

        fig = Figure(figsize=(5, 2.8), dpi=90, facecolor=BG_CARD)
        ax1 = fig.add_subplot(111)
        ax1.set_facecolor(BG_CARD)
        fig.subplots_adjust(left=0.10, right=0.88, top=0.92, bottom=0.18)

        color_temp = "#C2362A"   # DANGER / rojo
        color_hum = "#3B5F82"    # PRIMARY_LIGHT / azul

        if temps:
            xs_t = [p.ts for p in temps]
            ys_t = [p.temp for p in temps]
            ax1.plot(xs_t, ys_t, color=color_temp, linewidth=1.4, label="Temp °C")
        ax1.set_ylabel("Temperatura (°C)", fontsize=7, color=color_temp)
        ax1.tick_params(axis="y", labelsize=6, colors=color_temp)
        ax1.tick_params(axis="x", labelsize=6)

        if hums:
            ax2 = ax1.twinx()
            ax2.set_facecolor(BG_CARD)
            xs_h = [p.ts for p in hums]
            ys_h = [p.hum for p in hums]
            ax2.plot(xs_h, ys_h, color=color_hum, linewidth=1.4,
                     linestyle="--", label="Humedad %")
            ax2.set_ylabel("Humedad (%)", fontsize=7, color=color_hum)
            ax2.tick_params(axis="y", labelsize=6, colors=color_hum)
            ax2.set_ylim(0, 105)

        # Formato eje X
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M",
                                                            tz=self._local_tz))
        fig.autofmt_xdate(rotation=35, ha="right")

        # Leyenda combinada
        lines1, labels1 = ax1.get_legend_handles_labels()
        if hums:
            lines2, labels2 = ax2.get_legend_handles_labels()
            lines1 += lines2
            labels1 += labels2
        ax1.legend(lines1, labels1, fontsize=6, loc="upper left",
                   framealpha=0.7)

        ax1.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.5)

        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _build_kpis(self, parent: tk.Misc) -> None:
        d = self._data.kpi

        def fmt(val: float | None, decimals: int = 1) -> str:
            return f"{val:.{decimals}f}" if val is not None else _NO_DATA

        def delta(val: float | None) -> tuple[str, str]:
            if val is None:
                return _NO_DATA_DELTA, TEXT_SECONDARY
            return f"Prom. últimos {_DAYS} días", TEXT_SECONDARY

        t_val, t_dlt = fmt(d.avg_temp), delta(d.avg_temp)
        h_val, h_dlt = fmt(d.avg_hum, 0), delta(d.avg_hum)
        p_val, p_dlt = fmt(d.avg_pressure, 0), delta(d.avg_pressure)
        r_val = fmt(d.last_rain_24h) if d.last_rain_24h is not None else _NO_DATA
        r_dlt = ("Última lectura disponible", TEXT_SECONDARY) if d.last_rain_24h is not None \
            else (_NO_DATA_DELTA, TEXT_SECONDARY)

        _make_kpi(parent, "Temperatura exterior", t_val, "°C", t_dlt[0], t_dlt[1])
        _make_kpi(parent, "Humedad exterior",     h_val, "%",  h_dlt[0], h_dlt[1])
        _make_kpi(parent, "Presión atmosférica",  p_val, "hPa", p_dlt[0], p_dlt[1])
        _make_kpi(parent, "Lluvia últimas 24h",   r_val, "mm", r_dlt[0], r_dlt[1])

    def _build_events(self, parent: tk.Misc) -> None:
        card = _make_card(parent)
        card.pack(fill="x")

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="x")

        hdr = tk.Frame(inner, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, SPACE_MD))
        ttk.Label(hdr, text="Observaciones empíricas recientes",
                  style="CardH3.TLabel").pack(side="left")
        tk.Label(hdr, text="Ver todos →", bg=BG_CARD, fg=PRIMARY,
                 font=FONT_SMALL, cursor="hand2").pack(side="right")

        if not self._data.events:
            tk.Label(
                inner,
                text="Sin observaciones empíricas registradas todavía.",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w")
            return

        for ev in self._data.events:
            _make_event_row(inner, ev.ts_label, ev.title, ev.detail, ev.dot_color)


# ─── Helpers módulo-nivel ─────────────────────────────────────────────────────


def _make_card(parent: tk.Misc) -> tk.Frame:
    return tk.Frame(
        parent,
        bg=BG_CARD,
        highlightbackground=BORDER,
        highlightthickness=1,
    )


def _make_kpi(
    parent: tk.Misc,
    label: str,
    value: str,
    unit: str,
    delta: str,
    delta_color: str,
) -> None:
    card = _make_card(parent)
    card.pack(fill="x", pady=(0, SPACE_SM))
    inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
    inner.pack(fill="x")

    tk.Label(inner, text=label, bg=BG_CARD, fg=TEXT_SECONDARY,
             font=FONT_TINY, anchor="w").pack(fill="x")

    val_row = tk.Frame(inner, bg=BG_CARD)
    val_row.pack(fill="x", pady=(2, 0))

    tk.Label(val_row, text=value, bg=BG_CARD, fg=TEXT_PRIMARY,
             font=FONT_KPI_VALUE).pack(side="left")
    tk.Label(val_row, text=unit, bg=BG_CARD, fg=TEXT_SECONDARY,
             font=FONT_BODY).pack(side="left", padx=(SPACE_SM, 0),
                                  pady=(SPACE_MD, 0))
    tk.Label(inner, text=delta, bg=BG_CARD, fg=delta_color,
             font=FONT_TINY, anchor="w").pack(fill="x")


def _make_event_row(
    parent: tk.Misc,
    timestamp: str,
    title: str,
    detail: str,
    dot_color: str,
) -> None:
    row = tk.Frame(parent, bg=BG_CARD)
    row.pack(fill="x", pady=2)

    tk.Label(row, text="●", bg=BG_CARD, fg=dot_color,
             font=("DejaVu Sans", 12)).pack(side="left", padx=(0, SPACE_SM))
    tk.Label(row, text=timestamp, bg=BG_CARD, fg=TEXT_SECONDARY,
             font=FONT_BODY, width=12, anchor="w").pack(side="left")
    tk.Label(row, text=title, bg=BG_CARD, fg=TEXT_PRIMARY,
             font=FONT_BODY_BOLD, anchor="w").pack(side="left", padx=(SPACE_SM, 0))
    tk.Label(row, text=detail, bg=BG_CARD, fg=TEXT_SECONDARY,
             font=FONT_BODY, anchor="e").pack(side="right")
