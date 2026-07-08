"""Pantalla Admin/Datos.

Layout:

    ┌──────────────────────────────────────────────────────────┐
    │ Observaciones procesadas                                 │
    │ Datos meteorológicos validados del sensor                │
    │                                                          │
    │ [Carrusel rotativo de métrica destacada — 6s]            │
    │                                                          │
    │ Filtros: [Desde] [Hasta]    [Exportar CSV] [Exportar raw]│
    │                                                          │
    │ ┌──────────────────────────────────────────────────────┐ │
    │ │ Fecha │ Hora │ Temp │ Hum │ Presión │ Viento │ Lluvia│ │
    │ ├──────────────────────────────────────────────────────┤ │
    │ │ ...filas con doble-click para detalle...             │ │
    │ └──────────────────────────────────────────────────────┘ │
    └──────────────────────────────────────────────────────────┘

Lenguaje de dominio: "Observaciones procesadas" (no "sensor_data").
"""

from __future__ import annotations

import logging
import statistics
import threading
import tkinter as tk
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from yvy.application.use_cases.admin.export_data_csv import ExportDataCsvUseCase
from yvy.application.use_cases.admin.export_raw_csv import ExportRawCsvUseCase
from yvy.application.use_cases.admin.import_data_csv import ImportDataCsvUseCase
from yvy.domain.auth.models import User
from yvy.domain.auth.permissions import Permissions
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.presentation.components.data_detail_modal import DataDetailModal
from yvy.presentation.components.metric_carousel import (
    METRICS,
    MetricCarousel,
    MetricSnapshot,
)
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


# Default: últimos 7 días
DEFAULT_DAYS_BACK = 7


class DataView(tk.Frame):
    """Pantalla principal de Admin/Datos."""

    def __init__(
        self,
        parent: tk.Misc,
        factory: SQLiteConnectionFactory,
        export_data_uc: ExportDataCsvUseCase,
        export_raw_uc: ExportRawCsvUseCase,
        import_data_uc: ImportDataCsvUseCase,
        current_user: User | None,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)
        self._factory = factory
        self._export_data_uc = export_data_uc
        self._export_raw_uc = export_raw_uc
        self._import_data_uc = import_data_uc
        self._current_user = current_user

        # State de filtros
        now = datetime.now(UTC)
        self._date_to_var = tk.StringVar(
            value=now.strftime("%Y-%m-%d")
        )
        self._date_from_var = tk.StringVar(
            value=(now - timedelta(days=DEFAULT_DAYS_BACK)).strftime("%Y-%m-%d")
        )

        self._tree: ttk.Treeview | None = None
        self._observations_by_iid: dict[str, dict[str, Any]] = {}
        self._carousel: MetricCarousel | None = None

        self._build()
        self.refresh()

    # ─── Layout ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        container = tk.Frame(self, bg=BG_CREAM)
        container.pack(fill="both", expand=True, padx=SPACE_XL, pady=SPACE_XL)

        # Header textual
        ttk.Label(
            container, text="Mediciones", style="H1.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            container,
            text="Datos meteorológicos validados del sensor de la institución",
            style="Secondary.TLabel",
        ).pack(anchor="w", pady=(2, SPACE_LG))

        # Carrusel rotativo
        self._carousel = MetricCarousel(
            container,
            data_provider=self._compute_carousel_snapshots,
        )
        self._carousel.pack(fill="x", pady=(0, SPACE_LG))

        # Filtros + botones export
        controls = tk.Frame(container, bg=BG_CREAM)
        controls.pack(fill="x", pady=(0, SPACE_MD))

        self._build_filters(controls)
        self._build_export_buttons(controls)

        # Tabla
        card = tk.Frame(
            container,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=BG_CARD, padx=SPACE_XL, pady=SPACE_XL)
        inner.pack(fill="both", expand=True)

        columns = (
            "fecha", "hora", "temp_out", "hum_out",
            "pressure", "wind", "rain", "uv",
        )
        self._tree = ttk.Treeview(
            inner, columns=columns, show="headings", height=12,
        )
        self._tree.heading("fecha", text="Fecha")
        self._tree.heading("hora", text="Hora")
        self._tree.heading("temp_out", text="Temp ext (°C)")
        self._tree.heading("hum_out", text="Hum ext (%)")
        self._tree.heading("pressure", text="Presión (hPa)")
        self._tree.heading("wind", text="Viento (m/s)")
        self._tree.heading("rain", text="Lluvia 1h (mm)")
        self._tree.heading("uv", text="UV")

        for col in columns:
            self._tree.column(col, width=110, anchor="center")

        scrollbar = ttk.Scrollbar(inner, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", lambda _e: self._open_detail_for_selected())

        # Hint
        tk.Label(
            inner,
            text="Doble-click sobre una fila para ver el detalle completo.",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(SPACE_SM, 0))

    def _build_filters(self, parent: tk.Misc) -> None:
        filters = tk.Frame(parent, bg=BG_CREAM)
        filters.pack(side="left")

        tk.Label(
            filters, text="Desde:",
            bg=BG_CREAM, fg=TEXT_SECONDARY, font=FONT_SMALL,
        ).pack(side="left", padx=(0, SPACE_SM))
        ttk.Entry(filters, textvariable=self._date_from_var, width=12).pack(
            side="left", padx=(0, SPACE_MD)
        )

        tk.Label(
            filters, text="Hasta:",
            bg=BG_CREAM, fg=TEXT_SECONDARY, font=FONT_SMALL,
        ).pack(side="left", padx=(0, SPACE_SM))
        ttk.Entry(filters, textvariable=self._date_to_var, width=12).pack(
            side="left", padx=(0, SPACE_MD)
        )

        ttk.Button(
            filters, text="Aplicar filtro", command=self.refresh,
            style="Primary.TButton",
        ).pack(side="left")

    def _build_export_buttons(self, parent: tk.Misc) -> None:
        # Acciones a la derecha. Si ambos botones no caben, ponemos
        # el de raw en la siguiente fila (debajo de filtros).
        actions = tk.Frame(parent, bg=BG_CREAM)
        actions.pack(side="right")

        # Importar CSV: admin/superadmin/profesor
        if Permissions.can_import_data(self._current_user):
            ttk.Button(
                actions,
                text="Importar CSV",
                command=self._on_import_data_clicked,
                style="Primary.TButton",
            ).pack(side="left", padx=(0, SPACE_SM))

        # Export CSV procesado: cualquier admin/superadmin/profesor
        if Permissions.can_export_data(self._current_user):
            ttk.Button(
                actions,
                text="Exportar CSV procesado",
                command=self._on_export_data_clicked,
                style="Primary.TButton",
            ).pack(side="left", padx=(0, SPACE_SM))

        # Export raw: requiere flag
        if Permissions.can_export_raw(self._current_user):
            ttk.Button(
                actions,
                text="Exportar CSV crudo",
                command=self._on_export_raw_clicked,
                style="Primary.TButton",
            ).pack(side="left")

    # ─── Refresh ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        if self._tree is None:
            return

        date_from, date_to = self._parse_date_filters()
        if date_from is None or date_to is None:
            return  # Error ya mostrado

        for iid in self._tree.get_children():
            self._tree.delete(iid)
        self._observations_by_iid.clear()

        rows = self._fetch_observations(date_from, date_to)

        for r in rows:
            self._insert_row(dict(r))

        # Forzar re-render del carrusel con datos actualizados
        if self._carousel is not None:
            self._carousel._render_current()

    def _parse_date_filters(self) -> tuple[datetime | None, datetime | None]:
        try:
            d_from = datetime.strptime(self._date_from_var.get(), "%Y-%m-%d").replace(
                tzinfo=UTC,
            )
            d_to_raw = datetime.strptime(self._date_to_var.get(), "%Y-%m-%d").replace(
                tzinfo=UTC,
            )
            # date_to inclusive: extender al final del día
            d_to = d_to_raw + timedelta(hours=23, minutes=59, seconds=59)
        except ValueError:
            messagebox.showerror(
                "Filtro inválido",
                "Las fechas deben tener formato YYYY-MM-DD (ej: 2026-04-15).",
            )
            return None, None
        return d_from, d_to

    def _fetch_observations(
        self,
        date_from: datetime,
        date_to: datetime,
    ) -> list:
        conn = self._factory.get_connection()
        cur = conn.execute(
            """
            SELECT id, event_id, observed_at, pywws_mode,
                   temp_outdoor, temp_indoor, hum_outdoor, hum_indoor,
                   pressure_abs, pressure_rel,
                   wind_speed, wind_gust, wind_direction,
                   rain_1h, rain_24h, rain_total,
                   uv_index, solar_radiation,
                   is_valid, validation_notes
              FROM sensor_data
             WHERE observed_at >= ? AND observed_at <= ?
             ORDER BY observed_at DESC
             LIMIT 500
            """,
            (
                date_from.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                date_to.strftime("%Y-%m-%dT%H:%M:%S.999Z"),
            ),
        )
        return cur.fetchall()

    def _insert_row(self, obs: dict[str, Any]) -> None:
        assert self._tree is not None

        observed = obs.get("observed_at", "")
        _TZ_AR = timezone(timedelta(hours=-3))
        try:
            dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            dt_local = dt.astimezone(_TZ_AR)
            fecha_str = dt_local.strftime("%d/%m/%Y")
            hora_str  = dt_local.strftime("%H:%M")
        except (ValueError, AttributeError):
            fecha_str = observed[:10] if observed else "—"
            hora_str = observed[11:16] if len(observed) > 16 else "—"

        # Calcular dirección textual del viento si está
        wind_str = self._fmt(obs.get("wind_speed"))
        if obs.get("wind_direction") is not None:
            wind_str = f"{wind_str} ({self._wind_dir_text(obs['wind_direction'])})"

        iid = self._tree.insert(
            "", "end",
            values=(
                fecha_str,
                hora_str,
                self._fmt(obs.get("temp_outdoor")),
                self._fmt(obs.get("hum_outdoor")),
                self._fmt(obs.get("pressure_abs"), decimals=0),
                wind_str,
                self._fmt(obs.get("rain_1h")),
                self._fmt(obs.get("uv_index")),
            ),
        )
        # Guardar observed_at_local para el modal
        obs["observed_at_local"] = f"{fecha_str} {hora_str} (UTC-3)"
        self._observations_by_iid[iid] = obs

    @staticmethod
    def _fmt(value: float | None, decimals: int = 1) -> str:
        if value is None:
            return "—"
        return f"{value:.{decimals}f}"

    @staticmethod
    def _wind_dir_text(degrees: float) -> str:
        """Convierte grados a cardinales (NSEW + intermedios)."""
        dirs = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
        idx = int(((degrees + 22.5) % 360) // 45)
        return dirs[idx]

    # ─── Carrusel data provider ─────────────────────────────────────────

    def _compute_carousel_snapshots(self) -> dict[str, MetricSnapshot]:
        """Computa snapshots para las 8 métricas del carrusel.

        Strategy:
        - "current": valor más reciente en sensor_data (última fila).
        - "avg_24h": promedio sobre filas con observed_at >= now - 24hs.
        - "trend": comparación entre avg_24h y avg_24-48h previo.
        """
        conn = self._factory.get_connection()

        # Última observación (current values)
        cur = conn.execute(
            """
            SELECT temp_outdoor, temp_indoor, hum_outdoor, pressure_abs,
                   wind_speed, wind_direction, rain_1h, uv_index
              FROM sensor_data
             ORDER BY observed_at DESC
             LIMIT 1
            """
        )
        latest = cur.fetchone()

        # Avg últimas 24hs
        now = datetime.now(UTC)
        last_24h = now - timedelta(hours=24)
        prev_24h_start = now - timedelta(hours=48)

        cur = conn.execute(
            """
            SELECT temp_outdoor, temp_indoor, hum_outdoor, pressure_abs,
                   wind_speed, wind_direction, rain_1h, uv_index
              FROM sensor_data
             WHERE observed_at >= ?
            """,
            (last_24h.strftime("%Y-%m-%dT%H:%M:%S.000Z"),),
        )
        rows_24h = cur.fetchall()

        cur = conn.execute(
            """
            SELECT temp_outdoor, temp_indoor, hum_outdoor, pressure_abs,
                   wind_speed, wind_direction, rain_1h, uv_index
              FROM sensor_data
             WHERE observed_at >= ? AND observed_at < ?
            """,
            (
                prev_24h_start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                last_24h.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            ),
        )
        rows_prev = cur.fetchall()

        snapshots: dict[str, MetricSnapshot] = {}
        for spec in METRICS:
            current = latest[spec.column] if latest is not None else None

            avg_24 = self._safe_avg([r[spec.column] for r in rows_24h])
            avg_prev = self._safe_avg([r[spec.column] for r in rows_prev])

            trend = "flat"
            if avg_24 is not None and avg_prev is not None:
                if avg_24 > avg_prev * 1.02:  # 2% threshold
                    trend = "up"
                elif avg_24 < avg_prev * 0.98:
                    trend = "down"

            snapshots[spec.column] = MetricSnapshot(
                current=current, avg_24h=avg_24, trend=trend,
            )
        return snapshots

    @staticmethod
    def _safe_avg(values: list) -> float | None:
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        return statistics.mean(clean)

    # ─── Detail modal ───────────────────────────────────────────────────

    def _open_detail_for_selected(self) -> None:
        if self._tree is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        obs = self._observations_by_iid.get(sel[0])
        if obs is None:
            return
        DataDetailModal(self.winfo_toplevel(), observation=obs)

    # ─── Import handler ─────────────────────────────────────────────────

    def _on_import_data_clicked(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar CSV de datos IEA para importar",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not path:
            return

        actor = self._current_user

        def _run() -> None:
            try:
                from pathlib import Path as _Path
                result = self._import_data_uc.execute(
                    input_path=_Path(path),
                    actor_user_id=actor.id if actor else None,
                    actor_username=actor.username if actor else None,
                )
                msg = (
                    f"Importación completada:\n"
                    f"  • {result.rows_inserted} filas nuevas insertadas\n"
                    f"  • {result.rows_skipped} filas ya existentes (omitidas)\n"
                    f"  • {result.rows_error} filas con error de formato"
                )
                self.after(0, lambda: messagebox.showinfo("Importación completada", msg))
                self.after(0, self.refresh)
            except Exception as exc:
                logger.exception("Import sensor_data falló")
                self.after(0, lambda exc=exc: messagebox.showerror(
                    "Error al importar",
                    f"No se pudo importar el archivo:\n{exc}",
                ))

        threading.Thread(target=_run, daemon=True).start()

    # ─── Export handlers ────────────────────────────────────────────────

    def _on_export_data_clicked(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Guardar CSV de observaciones procesadas",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="export.csv",
        )
        if not path:
            return

        date_from, date_to = self._parse_date_filters()
        actor = self._current_user

        def _run() -> None:
            try:
                result = self._export_data_uc.execute(
                    output_path=Path(path),
                    date_from=date_from,
                    date_to=date_to,
                    actor_user_id=actor.id if actor else None,
                    actor_username=actor.username if actor else None,
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Exportación completada",
                    f"Se exportaron {result.rows_exported} filas a:\n{result.file_path}",
                ))
            except Exception as exc:
                logger.exception("Export sensor_data falló")
                self.after(0, lambda exc=exc: messagebox.showerror(
                    "Error",
                    f"No se pudo exportar:\n{exc}",
                ))

        threading.Thread(target=_run, daemon=True).start()

    def apply_theme(self, palette: dict) -> None:
        from yvy.presentation.theme_manager import recolor
        recolor(self, palette)
        if self._carousel is not None:
            self._carousel.apply_theme(palette)

    def _on_export_raw_clicked(self) -> None:
        # Doble validación de permisos defensiva
        if not Permissions.can_export_raw(self._current_user):
            messagebox.showerror(
                "Permiso denegado",
                "Tu cuenta no tiene permiso para exportar lecturas crudas.",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Guardar CSV de lecturas crudas (envío externo)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="export_raw.csv",
        )
        if not path:
            return

        date_from, date_to = self._parse_date_filters()
        actor = self._current_user

        def _run() -> None:
            try:
                result = self._export_raw_uc.execute(
                    output_path=Path(path),
                    date_from=date_from,
                    date_to=date_to,
                    actor_user_id=actor.id if actor else None,
                    actor_username=actor.username if actor else None,
                )
                self.after(0, lambda: messagebox.showinfo(
                    "Exportación completada",
                    f"Se exportaron {result.rows_exported} filas a:\n{result.file_path}",
                ))
            except Exception as exc:
                logger.exception("Export sensor_raw falló")
                self.after(0, lambda exc=exc: messagebox.showerror(
                    "Error",
                    f"No se pudo exportar:\n{exc}",
                ))

        threading.Thread(target=_run, daemon=True).start()
