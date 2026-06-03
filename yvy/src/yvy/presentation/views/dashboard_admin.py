"""Dashboard del profesor/admin.

Layout general:

    [Título "Dashboard"]                         [Exportar*]
    [Subtítulo]

    ┌─ chart card (expand) ──────────────────┐  ┌─ KPI (260px) ──┐
    │ [controles si no es alumno]            │  │ Temperatura    │
    │ ─────────────────────────────────────  │  ├────────────────┤
    │ [ChartWidget — matplotlib embebido]    │  │ Humedad        │
    └────────────────────────────────────────┘  ├────────────────┤
                                                │ Presión        │
    [Diagnóstico del día]                       ├────────────────┤
                                                │ VPD actual     │
    [Observaciones empíricas recientes]         └────────────────┘

* Exportar decorativo — TODO

Role gating del área de gráfico:
    alumno      → sin selectores, fijo: VPD / 24h
    otros       → Combobox "Gráfico" + radio "Período" (24h/7d/30d)
                  Default: VPD — Riesgo agroclimático / 7d
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any

import tkinter as tk
from tkinter import ttk

from yvy.presentation.charts import SENSOR_CHARTS
from yvy.presentation.components.chart_widget import ChartWidget
from yvy.presentation.components.help_button import HelpButton
from yvy.presentation.theme import (
    ACCENT_GOLD,
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
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

if TYPE_CHECKING:
    from yvy.application.use_cases.compute_derived import (
        ComputeDerivedUseCase,
        CurrentDerivedValues,
    )
    from yvy.application.use_cases.query_sensor_aggregated import (
        QuerySensorAggregatedUseCase,
    )
    from yvy.infrastructure.help.help_repository import HelpRepository
    from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory

logger = logging.getLogger(__name__)

_DAYS = 7
_NO_DATA = "—"
_NO_DATA_DELTA = "sin datos suficientes"

# Mapa display label → clave en SENSOR_CHARTS (preserva orden de inserción)
_CHART_LABEL_TO_KEY: dict[str, str] = {
    chart.label: key for key, chart in SENSOR_CHARTS.items()
}
_CHART_LABELS: list[str] = list(_CHART_LABEL_TO_KEY.keys())
_DEFAULT_CHART_LABEL = SENSOR_CHARTS["vpd"].label   # "VPD — Riesgo agroclimático"
_DEFAULT_PERIOD = "7d"
_PERIODS = ["24h", "7d", "30d"]

_KPI_CARD_WIDTH = 260

# Mapa chart key → help article key para el HelpButton del gráfico
_CHART_KEY_TO_HELP: dict[str, str] = {
    "vpd":              "glosario_vpd",
    "temperatura":      "glosario_temperatura",
    "humedad":          "glosario_humedad",
    "presion":          "glosario_presion",
    "viento":           "glosario_viento",
    "lluvia":           "glosario_lluvia_uv",
    "punto_rocio":      "glosario_dewpoint",
    "amplitud_termica": "glosario_amplitud_termica",
    "presion_tendencia":"glosario_tendencia_presion",
}


# ─── Dataclasses internos ─────────────────────────────────────────────────────


@dataclass
class _KpiData:
    avg_temp: float | None = None
    avg_hum: float | None = None
    avg_pressure: float | None = None
    last_rain_24h: float | None = None
    row_count: int = 0


@dataclass
class _DerivedKpiData:
    """Datos derivados calculados por ComputeDerivedUseCase."""
    vpd: float | None = None
    vpd_zone_label: str = "—"
    vpd_zone_color: str = "#6B7280"
    today_rain_mm: float | None = None
    day_summary: str = ""


@dataclass
class _EventRow:
    ts_label: str
    title: str
    detail: str
    dot_color: str = SUCCESS


@dataclass
class _DashboardData:
    kpi: _KpiData = field(default_factory=_KpiData)
    events: list[_EventRow] = field(default_factory=list)


# ─── View ─────────────────────────────────────────────────────────────────────


class DashboardAdminView(tk.Frame):
    """Dashboard con KPIs reales, gráfico seleccionable y eventos empíricos.

    Args:
        parent: widget padre.
        db_factory: conexión DB para KPIs y eventos. Si None, muestra «—».
        local_tz: zona horaria para timestamps de eventos.
        query_sensor_aggregated_uc: use case para los gráficos. Si None,
            el área de gráfico muestra "Sin conexión al sistema de sensores".
        current_user: usuario activo (User o MockUser). Determina role gating.
        station_uuid: UUID de la estación para las queries de gráfico.
        compute_derived_uc: use case de indicadores derivados. Si None,
            el KPI de VPD y el diagnóstico muestran «—».
    """

    def __init__(
        self,
        parent: tk.Misc,
        db_factory: SQLiteConnectionFactory | None = None,
        local_tz: tzinfo | None = None,
        query_sensor_aggregated_uc: QuerySensorAggregatedUseCase | None = None,
        current_user: Any = None,
        station_uuid: str | None = None,
        compute_derived_uc: ComputeDerivedUseCase | None = None,
        help_repository: HelpRepository | None = None,
        open_pizarra: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)

        self._db_factory = db_factory
        self._local_tz = local_tz or UTC
        self._query_uc = query_sensor_aggregated_uc
        self._current_user = current_user
        self._station_uuid = station_uuid or ""
        self._compute_derived_uc = compute_derived_uc
        self._help_repo = help_repository
        self._open_pizarra = open_pizarra

        # Widgets del área de gráfico (inicializados en _build)
        self._chart_widget: ChartWidget | None = None
        self._chart_combo: ttk.Combobox | None = None
        self._period_var: tk.StringVar | None = None
        self._chart_help_btn: HelpButton | None = None  # HelpButton dinámico del gráfico
        self._chart_title_lbl: tk.Label | None = None
        # Para alumno (sin selectors), el chart key y period son fijos
        self._alumno_chart_key: str = "vpd"
        self._alumno_period: str = "24h"

        self._data = self._load_data()
        self._derived = self._load_derived()
        self._build()

    # ─── Helpers de rol ──────────────────────────────────────────────────

    def _get_role(self) -> str:
        """Rol normalizado en minúsculas desde User o MockUser."""
        role = getattr(self._current_user, "role", None)
        if role is None:
            return "alumno"
        if hasattr(role, "value"):          # Role enum
            return role.value.lower()
        return str(role).lower()

    def _is_alumno(self) -> bool:
        return self._get_role() == "alumno"

    # ─── Queries de KPI y eventos ────────────────────────────────────────

    def _load_data(self) -> _DashboardData:
        if self._db_factory is None:
            return _DashboardData()
        try:
            conn = self._db_factory.get_connection()
            return _DashboardData(
                kpi=self._query_kpis(conn),
                events=self._query_events(conn),
            )
        except Exception:
            logger.exception("Error cargando datos del dashboard")
            return _DashboardData()

    def _load_derived(self) -> _DerivedKpiData:
        """Calcula indicadores derivados vía ComputeDerivedUseCase."""
        if self._compute_derived_uc is None or self._query_uc is None:
            return _DerivedKpiData()
        try:
            result = self._compute_derived_uc.execute_current(
                self._query_uc, self._station_uuid
            )
            return _DerivedKpiData(
                vpd=result.vpd,
                vpd_zone_label=result.vpd_zone_label,
                vpd_zone_color=result.vpd_zone_color,
                today_rain_mm=result.today_rain_mm,
                day_summary=result.day_summary,
            )
        except Exception:
            logger.exception("Error calculando indicadores derivados")
            return _DerivedKpiData()

    def _query_kpis(self, conn) -> _KpiData:  # type: ignore[no-untyped-def]
        since = (datetime.now(UTC) - timedelta(days=_DAYS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        row = conn.execute(
            """
            SELECT
                AVG(CASE WHEN temp_outdoor IS NOT NULL THEN temp_outdoor END),
                AVG(CASE WHEN hum_outdoor  IS NOT NULL THEN hum_outdoor  END),
                AVG(CASE WHEN pressure_rel IS NOT NULL THEN pressure_rel END),
                COUNT(*)
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
            """
        ).fetchone()

        return _KpiData(
            avg_temp=float(row[0]) if row and row[0] is not None else None,
            avg_hum=float(row[1]) if row and row[1] is not None else None,
            avg_pressure=float(row[2]) if row and row[2] is not None else None,
            last_rain_24h=(
                float(rain_row[0]) if rain_row and rain_row[0] is not None else None
            ),
            row_count=int(row[3]) if row else 0,
        )

    def _query_events(self, conn) -> list[_EventRow]:  # type: ignore[no-untyped-def]
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

        events: list[_EventRow] = []
        for r in rows:
            try:
                ts = datetime.fromisoformat(
                    str(r[0]).replace("Z", "+00:00")
                ).astimezone(self._local_tz)
                ts_label = ts.strftime("%d/%m %H:%M")
            except Exception:
                ts_label = str(r[0])[:16] if r[0] else _NO_DATA

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
        if self._derived.day_summary:
            self._build_day_summary(container, self._derived.day_summary)
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
        # TODO: implementar exportación de datos en fase posterior
        ttk.Button(
            actions,
            text="Exportar",
            style="Secondary.TButton",
            state="disabled",
        ).pack(side="left")

    def _build_body(self, parent: tk.Misc) -> None:
        body = tk.Frame(parent, bg=BG_CREAM)
        body.pack(fill="both", expand=True, pady=(0, SPACE_LG))

        # Área de gráfico — izquierda, expande
        chart_card = _make_card(body)
        chart_card.pack(side="left", fill="both", expand=True, padx=(0, SPACE_LG))
        self._build_chart_area(chart_card)

        # KPI cards — derecha, ancho fijo
        kpi_col = tk.Frame(body, bg=BG_CREAM, width=_KPI_CARD_WIDTH)
        kpi_col.pack(side="right", fill="y")
        kpi_col.pack_propagate(False)
        self._build_kpis(kpi_col)

    def _build_chart_area(self, card: tk.Frame) -> None:
        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        inner.pack(fill="both", expand=True)

        if not self._is_alumno():
            self._build_chart_controls(inner)

        # Header del gráfico con HelpButton dinámico
        chart_hdr = tk.Frame(inner, bg=BG_CARD)
        chart_hdr.pack(fill="x", pady=(0, SPACE_SM))
        self._chart_title_lbl = tk.Label(
            chart_hdr,
            text=_DEFAULT_CHART_LABEL,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
        )
        self._chart_title_lbl.pack(side="left")

        default_help_key = _CHART_KEY_TO_HELP.get("vpd", "glosario_vpd")
        if self._help_repo is not None:
            self._chart_help_btn = HelpButton(
                chart_hdr,
                help_repository=self._help_repo,
                article_key=default_help_key,
                on_expand=self._open_pizarra,
                bg=BG_CARD,
            )
            self._chart_help_btn.pack(side="left", padx=(SPACE_SM, 0))

        self._chart_widget = ChartWidget(inner, width_px=560, height_px=290)
        self._chart_widget.pack(fill="both", expand=True)

        # Primer render diferido 80ms para que Tk asiente el layout
        self.after(80, self._trigger_render)

    def _build_chart_controls(self, parent: tk.Frame) -> None:
        """Barra de selectores: Combobox de gráfico + radio de período."""
        bar = tk.Frame(parent, bg=BG_CARD)
        bar.pack(fill="x", pady=(0, SPACE_MD))

        # ── Selector de gráfico ────────────────────────────────────────
        tk.Label(
            bar, text="Gráfico:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY
        ).pack(side="left", padx=(0, SPACE_SM))

        self._chart_combo = ttk.Combobox(
            bar,
            values=_CHART_LABELS,
            state="readonly",
            width=22,
            font=FONT_BODY,
        )
        self._chart_combo.set(_DEFAULT_CHART_LABEL)
        self._chart_combo.pack(side="left")
        self._chart_combo.bind("<<ComboboxSelected>>", lambda _: self._trigger_render())

        # ── Separador visual ───────────────────────────────────────────
        tk.Frame(bar, bg=BG_CARD, width=SPACE_XL).pack(side="left")

        # ── Selector de período ────────────────────────────────────────
        tk.Label(
            bar, text="Período:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY
        ).pack(side="left", padx=(0, SPACE_SM))

        self._period_var = tk.StringVar(value=_DEFAULT_PERIOD)
        for p in _PERIODS:
            ttk.Radiobutton(
                bar,
                text=p,
                variable=self._period_var,
                value=p,
                command=self._trigger_render,
            ).pack(side="left", padx=(0, SPACE_SM))

    def _make_help_btn(self, parent: tk.Misc, key: str) -> HelpButton | None:
        """Crea un HelpButton si hay help_repo; None si no."""
        if self._help_repo is None:
            return None
        return HelpButton(
            parent,
            help_repository=self._help_repo,
            article_key=key,
            on_expand=self._open_pizarra,
            bg=BG_CARD,
        )

    def _build_kpis(self, parent: tk.Misc) -> None:
        d = self._data.kpi
        dv = self._derived

        def fmt(val: float | None, decimals: int = 1) -> str:
            return f"{val:.{decimals}f}" if val is not None else _NO_DATA

        def delta(val: float | None) -> tuple[str, str]:
            if val is None:
                return _NO_DATA_DELTA, TEXT_SECONDARY
            return f"Prom. últimos {_DAYS} días", TEXT_SECONDARY

        t_delta = delta(d.avg_temp)
        h_delta = delta(d.avg_hum)
        p_delta = delta(d.avg_pressure)

        _make_kpi(parent, "Temperatura exterior", fmt(d.avg_temp),        "°C",  t_delta[0], t_delta[1],
                  help_widget=self._make_help_btn(parent, "glosario_temperatura"))
        _make_kpi(parent, "Humedad exterior",     fmt(d.avg_hum, 0),      "%",   h_delta[0], h_delta[1],
                  help_widget=self._make_help_btn(parent, "glosario_humedad"))
        _make_kpi(parent, "Presión atmosférica",  fmt(d.avg_pressure, 0), "hPa", p_delta[0], p_delta[1],
                  help_widget=self._make_help_btn(parent, "glosario_presion"))
        _make_kpi_vpd(
            parent,
            vpd_value=dv.vpd,
            vpd_zone_label=dv.vpd_zone_label,
            vpd_zone_color=dv.vpd_zone_color,
            today_rain_mm=dv.today_rain_mm,
            help_widget=self._make_help_btn(parent, "glosario_vpd"),
        )

    def _build_day_summary(self, parent: tk.Misc, summary_text: str) -> None:
        """Sección 'Diagnóstico del día' con texto generado automáticamente."""
        if not summary_text:
            return

        card = _make_card(parent)
        card.pack(fill="x", pady=(0, SPACE_SM))

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_MD)
        inner.pack(fill="x")

        title_row = tk.Frame(inner, bg=BG_CARD)
        title_row.pack(fill="x", anchor="w")
        tk.Label(
            title_row,
            text="Diagnóstico del día",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_SMALL,
            anchor="w",
        ).pack(side="left")
        if self._help_repo is not None:
            HelpButton(
                title_row,
                help_repository=self._help_repo,
                article_key="glosario_observacion_yvy",
                on_expand=self._open_pizarra,
                bg=BG_CARD,
            ).pack(side="left", padx=(SPACE_SM, 0))

        tk.Label(
            inner,
            text=summary_text,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            anchor="w",
            justify="left",
            wraplength=_KPI_CARD_WIDTH * 3,   # ancho generoso — se adapta al layout
        ).pack(anchor="w", pady=(SPACE_SM // 2, 0))

    def _build_events(self, parent: tk.Misc) -> None:
        card = _make_card(parent)
        card.pack(fill="x")

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_LG)
        inner.pack(fill="x")

        hdr = tk.Frame(inner, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, SPACE_MD))
        ttk.Label(
            hdr, text="Observaciones empíricas recientes", style="CardH3.TLabel"
        ).pack(side="left")
        if self._help_repo is not None:
            HelpButton(
                hdr,
                help_repository=self._help_repo,
                article_key="uso_cargar_observacion",
                on_expand=self._open_pizarra,
                bg=BG_CARD,
            ).pack(side="left", padx=(SPACE_SM, 0))
        tk.Label(
            hdr, text="Ver todos →", bg=BG_CARD, fg=PRIMARY,
            font=FONT_SMALL, cursor="hand2"
        ).pack(side="right")

        if not self._data.events:
            tk.Label(
                inner,
                text="Sin eventos recientes.",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(anchor="w")
            return

        for ev in self._data.events:
            _make_event_row(inner, ev.ts_label, ev.title, ev.detail, ev.dot_color)

    # ─── Tema ────────────────────────────────────────────────────────────

    def apply_theme(self, palette: dict) -> None:
        """Reconfigura todos los widgets del dashboard con la paleta dada."""
        from yvy.presentation.theme_manager import recolor
        recolor(self, palette)

    # ─── Render del gráfico ───────────────────────────────────────────────

    def _current_chart_key(self) -> str:
        if self._is_alumno():
            return self._alumno_chart_key
        if self._chart_combo is not None:
            label = self._chart_combo.get()
            return _CHART_LABEL_TO_KEY.get(label, "temperatura")
        return "temperatura"

    def _current_period(self) -> str:
        if self._is_alumno():
            return self._alumno_period
        if self._period_var is not None:
            return self._period_var.get()
        return _DEFAULT_PERIOD

    def _trigger_render(self) -> None:
        """Dispara o re-dispara el chart con la selección actual."""
        if self._chart_widget is None:
            return

        chart_key = self._current_chart_key()

        # Actualizar HelpButton del gráfico según la selección actual
        if self._chart_help_btn is not None:
            help_key = _CHART_KEY_TO_HELP.get(chart_key)
            if help_key:
                self._chart_help_btn.update_article_key(help_key)
        if hasattr(self, "_chart_title_lbl") and self._chart_title_lbl is not None:
            label = self._chart_combo.get() if self._chart_combo else _DEFAULT_CHART_LABEL
            self._chart_title_lbl.configure(text=label)

        if self._query_uc is None:
            self._chart_widget.show_empty("Sin conexión al sistema de sensores")
            return

        period = self._current_period()
        station_uuid = self._station_uuid
        query_uc = self._query_uc

        chart = SENSOR_CHARTS.get(chart_key)
        if chart is None:
            self._chart_widget.show_error(f"Gráfico '{chart_key}' no encontrado")
            return

        # Captura explícita de variables para evitar closure tardío en el thread
        self._chart_widget.render(
            lambda fig, ax, c=chart, p=period, s=station_uuid: c.render(
                fig, ax, p, s, query_uc
            )
        )


# ─── Helpers módulo-nivel ──────────────────────────────────────────────────────


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
    help_widget: tk.Widget | None = None,
) -> None:
    card = _make_card(parent)
    card.pack(fill="x", pady=(0, SPACE_SM))

    inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
    inner.pack(fill="x")

    label_row = tk.Frame(inner, bg=BG_CARD)
    label_row.pack(fill="x")
    tk.Label(
        label_row, text=label, bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_TINY, anchor="w"
    ).pack(side="left")
    if help_widget is not None:
        help_widget.pack(side="left", padx=(6, 0))

    val_row = tk.Frame(inner, bg=BG_CARD)
    val_row.pack(fill="x", pady=(2, 0))
    tk.Label(val_row, text=value, bg=BG_CARD, fg=TEXT_PRIMARY, font=FONT_KPI_VALUE).pack(
        side="left"
    )
    tk.Label(
        val_row, text=unit, bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY
    ).pack(side="left", padx=(SPACE_SM, 0), pady=(SPACE_MD, 0))

    tk.Label(
        inner, text=delta, bg=BG_CARD, fg=delta_color, font=FONT_TINY, anchor="w"
    ).pack(fill="x")


def _make_kpi_vpd(
    parent: tk.Misc,
    vpd_value: float | None,
    vpd_zone_label: str,
    vpd_zone_color: str,
    today_rain_mm: float | None,
    help_widget: tk.Widget | None = None,
) -> None:
    """KPI card de VPD con zona agroclimática y lluvia de hoy.

    Muestra:
        - Etiqueta "VPD actual"
        - Valor en kPa (coloreado con color de zona)
        - Zona agroclimática como delta (mismo color)
        - Lluvia de hoy como línea secundaria pequeña
    """
    card = _make_card(parent)
    card.pack(fill="x", pady=(0, SPACE_SM))

    inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_LG, pady=SPACE_MD)
    inner.pack(fill="x")

    label_row = tk.Frame(inner, bg=BG_CARD)
    label_row.pack(fill="x")
    tk.Label(
        label_row, text="VPD actual", bg=BG_CARD, fg=TEXT_SECONDARY,
        font=FONT_TINY, anchor="w"
    ).pack(side="left")
    if help_widget is not None:
        help_widget.pack(side="left", padx=(6, 0))

    val_row = tk.Frame(inner, bg=BG_CARD)
    val_row.pack(fill="x", pady=(2, 0))

    vpd_str = f"{vpd_value:.2f}" if vpd_value is not None else _NO_DATA
    tk.Label(
        val_row, text=vpd_str, bg=BG_CARD,
        fg=vpd_zone_color if vpd_value is not None else TEXT_SECONDARY,
        font=FONT_KPI_VALUE,
    ).pack(side="left")
    tk.Label(
        val_row, text="kPa", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY
    ).pack(side="left", padx=(SPACE_SM, 0), pady=(SPACE_MD, 0))

    # Zona como delta
    zone_text = vpd_zone_label if vpd_value is not None else _NO_DATA_DELTA
    zone_color = vpd_zone_color if vpd_value is not None else TEXT_SECONDARY
    tk.Label(
        inner, text=zone_text, bg=BG_CARD, fg=zone_color,
        font=FONT_TINY, anchor="w"
    ).pack(fill="x")

    # Lluvia hoy
    if today_rain_mm is not None:
        rain_text = (
            f"Lluvia hoy: {today_rain_mm:.1f} mm"
            if today_rain_mm > 0
            else "Sin lluvia hoy"
        )
    else:
        rain_text = "Lluvia hoy: —"
    tk.Label(
        inner, text=rain_text, bg=BG_CARD, fg=TEXT_SECONDARY,
        font=FONT_TINY, anchor="w"
    ).pack(fill="x", pady=(2, 0))


def _make_event_row(
    parent: tk.Misc,
    timestamp: str,
    title: str,
    detail: str,
    dot_color: str,
) -> None:
    row = tk.Frame(parent, bg=BG_CARD)
    row.pack(fill="x", pady=2)

    tk.Label(
        row, text="●", bg=BG_CARD, fg=dot_color, font=("DejaVu Sans", 12)
    ).pack(side="left", padx=(0, SPACE_SM))
    tk.Label(
        row, text=timestamp, bg=BG_CARD, fg=TEXT_SECONDARY,
        font=FONT_BODY, width=12, anchor="w"
    ).pack(side="left")
    tk.Label(
        row, text=title, bg=BG_CARD, fg=TEXT_PRIMARY,
        font=FONT_BODY, anchor="w"
    ).pack(side="left", padx=(SPACE_SM, 0))
    tk.Label(
        row, text=detail, bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY, anchor="e"
    ).pack(side="right")
