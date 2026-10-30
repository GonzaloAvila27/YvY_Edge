"""Vista de listado de observaciones empíricas.

Tabla Treeview con paginación cursor-based, filtros por fecha y observador,
toggle de solo-válidas, botón para abrir wizard de carga y botón para
ver detalle de cualquier observación seleccionada.
"""

from __future__ import annotations

import logging
import tkinter as tk
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from tkinter import ttk
from zoneinfo import ZoneInfo

from yvy.domain.auth.models import User
from yvy.domain.auth.permissions import Permissions
from yvy.domain.empirical.models import EmpiricalObservation
from yvy.presentation.controllers.empirical_controller import EmpiricalController
from yvy.presentation.theme import COLORS, FONTS, SPACE_LG, SPACE_MD, SPACE_SM

logger = logging.getLogger(__name__)

_TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")


class EmpiricalListView(tk.Frame):
    """Listado de observaciones empíricas.

    Accesible desde sidebar para alumnos/profesores/admins. Cualquier
    usuario activo ve sus propias observaciones más las del resto;
    si los profesores/admins quieren filtrar por uno, hay combo de
    observador (en Fase 8.5b, no acá).
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: EmpiricalController,
        current_user: User,
        on_open_wizard: Callable[[], None],
        on_open_detail: Callable[[uuid.UUID], None],
    ) -> None:
        super().__init__(parent, bg=COLORS["bg"])
        self._controller = controller
        self._current_user = current_user
        self._on_open_wizard = on_open_wizard
        self._on_open_detail = on_open_detail

        # State de filtros
        self._only_valid_var = tk.BooleanVar(value=False)
        self._date_range_days_var = tk.StringVar(value="7")  # 1, 7, 30, "todos"
        self._current_rows: list[EmpiricalObservation] = []

        self._build_layout()
        self.refresh()

    def _build_layout(self) -> None:
        # Header
        header = tk.Frame(self, bg=COLORS["bg"], height=70)
        header.pack(side="top", fill="x", padx=SPACE_LG, pady=SPACE_LG)
        header.pack_propagate(False)

        tk.Label(
            header,
            text="Cuaderno empírico",
            font=FONTS["heading"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(side="left", anchor="w")

        # Botón cargar nueva observación (alumnos/profes/admins)
        if Permissions.can_create_empirical_observation(self._current_user):
            ttk.Button(
                header,
                text="+ Cargar observación",
                style="Primary.TButton",
                command=self._on_open_wizard,
            ).pack(side="right", padx=SPACE_SM)

        ttk.Button(
            header,
            text="Refrescar",
            style="Secondary.TButton",
            command=self.refresh,
        ).pack(side="right", padx=SPACE_SM)

        # Barra de filtros
        filters_frame = tk.Frame(self, bg=COLORS["bg_alt"], height=50)
        filters_frame.pack(side="top", fill="x", padx=SPACE_LG)
        filters_frame.pack_propagate(False)

        tk.Label(filters_frame, text="Período:", font=FONTS["body"], bg=COLORS["bg_alt"]).pack(
            side="left", padx=(SPACE_MD, SPACE_SM)
        )
        for days, label in [
            ("1", "Hoy"),
            ("7", "Última semana"),
            ("30", "Último mes"),
            ("0", "Todo"),
        ]:
            ttk.Radiobutton(
                filters_frame,
                text=label,
                variable=self._date_range_days_var,
                value=days,
                command=self.refresh,
            ).pack(side="left", padx=SPACE_SM)

        ttk.Checkbutton(
            filters_frame,
            text="Solo válidas",
            variable=self._only_valid_var,
            command=self.refresh,
        ).pack(side="left", padx=SPACE_LG)

        self._count_label = tk.Label(
            filters_frame,
            text="",
            font=FONTS["small"],
            bg=COLORS["bg_alt"],
            fg=COLORS["text_muted"],
        )
        self._count_label.pack(side="right", padx=SPACE_MD)

        # Tabla
        tree_frame = tk.Frame(self, bg=COLORS["bg"])
        tree_frame.pack(side="top", fill="both", expand=True, padx=SPACE_LG, pady=SPACE_MD)

        columns = ("fecha", "hora", "observador", "temp", "lluvia", "cielo", "viento", "calidad")
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
        self._tree.heading("fecha", text="Fecha")
        self._tree.heading("hora", text="Hora")
        self._tree.heading("observador", text="Observador")
        self._tree.heading("temp", text="T°C")
        self._tree.heading("lluvia", text="Lluvia mm")
        self._tree.heading("cielo", text="Cielo %")
        self._tree.heading("viento", text="Viento")
        self._tree.heading("calidad", text="Calidad")

        self._tree.column("fecha", width=90, anchor="center")
        self._tree.column("hora", width=60, anchor="center")
        self._tree.column("observador", width=140)
        self._tree.column("temp", width=60, anchor="center")
        self._tree.column("lluvia", width=80, anchor="center")
        self._tree.column("cielo", width=60, anchor="center")
        self._tree.column("viento", width=80, anchor="center")
        self._tree.column("calidad", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)

        self._tree.bind("<Double-1>", self._on_row_double_click)

        # Footer con botón ver detalle (alternativa al doble click)
        footer = tk.Frame(self, bg=COLORS["bg"], height=50)
        footer.pack(side="bottom", fill="x", padx=SPACE_LG, pady=SPACE_MD)
        footer.pack_propagate(False)

        ttk.Button(
            footer,
            text="Ver detalle",
            style="Secondary.TButton",
            command=self._open_detail_for_selected,
        ).pack(side="right")

    def apply_theme(self, palette: dict) -> None:
        from yvy.presentation.theme_manager import recolor

        recolor(self, palette)

    def refresh(self) -> None:
        """Recarga las filas según los filtros actuales."""
        # Limpiar tabla
        for item in self._tree.get_children():
            self._tree.delete(item)

        date_from = self._compute_date_from()
        only_valid = self._only_valid_var.get()

        try:
            observations = self._controller.list_observations(
                date_from=date_from,
                only_valid=only_valid,
                limit=100,
            )
        except Exception as exc:
            logger.exception("Error refrescando observaciones: %s", exc)
            self._count_label.config(text=f"Error: {exc}")
            return

        self._current_rows = observations

        for obs in observations:
            self._tree.insert(
                "",
                "end",
                iid=str(obs.observation_id),
                values=(
                    obs.observed_at_local.strftime("%d/%m/%Y"),
                    obs.observed_at_local.strftime("%H:%M"),
                    f"user#{obs.created_by_user_id}",  # TODO Fase 8.5b: resolver username vía repo
                    _fmt_or_dash(obs.temp_c, 1),
                    _fmt_or_dash(obs.rain_mm, 1),
                    f"{obs.sky_coverage_pct}%" if obs.sky_coverage_pct is not None else "—",
                    f"Beaufort {obs.wind_beaufort}" if obs.wind_beaufort is not None else "—",
                    "OK" if obs.is_valid else "Revisar",
                ),
                tags=("invalid",) if not obs.is_valid else (),
            )

        # Colorear filas inválidas
        self._tree.tag_configure("invalid", background=COLORS.get("warning_bg", "#FFF3CD"))

        self._count_label.config(text=f"{len(observations)} observaciones")

    def _compute_date_from(self) -> datetime | None:
        """Devuelve el datetime de corte según el filtro de período."""
        days_str = self._date_range_days_var.get()
        if days_str == "0":
            return None
        days = int(days_str)
        return datetime.now(_TZ_AR) - timedelta(days=days)

    def _on_row_double_click(self, _event) -> None:
        self._open_detail_for_selected()

    def _open_detail_for_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        try:
            obs_id = uuid.UUID(selection[0])
        except ValueError:
            return
        self._on_open_detail(obs_id)


def _fmt_or_dash(value: float | int | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"
