"""Modal de detalle: observación completa + eventos del día asociados.

Read-only. No permite edición (decisión cerrada Fase 8.5a). En 8.5b se
agregará botón "marcar discrepancia" para docentes.
"""

from __future__ import annotations

import logging
import tkinter as tk
import uuid
from tkinter import ttk

from yvy.domain.empirical.enums import (
    BEAUFORT_DESCRIPTIONS,
    CLOUD_TYPE_DESCRIPTIONS,
)
from yvy.domain.empirical.models import EmpiricalEvent
from yvy.presentation.controllers.empirical_controller import EmpiricalController
from yvy.presentation.theme import COLORS, FONTS, SPACE_LG, SPACE_MD, SPACE_SM

logger = logging.getLogger(__name__)


# Etiquetas legibles para los flags de calidad en validation_notes
_QUALITY_FLAG_LABELS: dict[str, str] = {
    "temp_c": "temperatura sin cargar",
    "rain_mm": "lluvia sin cargar",
    "sky_coverage_pct": "cobertura del cielo sin cargar",
    "wind_direction": "dirección del viento sin cargar",
    "wind_beaufort": "intensidad del viento sin cargar",
    "temp_c_out_of_range": "temperatura fuera de rango",
    "rain_mm_out_of_range": "lluvia fuera de rango",
}


class EmpiricalDetailModal(tk.Toplevel):
    """Modal de detalle de una observación.

    Carga el detalle vía controller (que llama al use case
    GetObservationDetails) en construcción. Si la observación no existe,
    cierra el modal inmediatamente con error visible.
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: EmpiricalController,
        observation_id: uuid.UUID,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._observation_id = observation_id

        self.title("Detalle de observación")
        self.configure(bg=COLORS["bg"])
        self.geometry("700x650")
        self.transient(parent.winfo_toplevel())  # type: ignore[arg-type]
        self.grab_set()

        try:
            self._detail = self._controller.get_observation_details(observation_id)
        except Exception as exc:
            logger.exception("Error cargando detalle: %s", exc)
            tk.Label(self, text=f"Error: {exc}", bg=COLORS["bg"]).pack(padx=SPACE_LG, pady=SPACE_LG)
            return

        if self._detail is None:
            tk.Label(self, text="Observación no encontrada.", bg=COLORS["bg"]).pack(padx=SPACE_LG, pady=SPACE_LG)
            return

        self._build_layout()

    def _build_layout(self) -> None:
        obs = self._detail.observation

        # Header
        header = tk.Frame(self, bg=COLORS["primary"], height=70)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text=f"Observación · {obs.observed_at_local.strftime('%d/%m/%Y %H:%M')}",
            font=FONTS["heading"], bg=COLORS["primary"], fg=COLORS["text_inverse"],
        ).pack(side="left", padx=SPACE_LG, pady=SPACE_SM, anchor="w")

        # Badge de calidad
        quality_bg = COLORS.get("success", "#28A745") if obs.is_valid else COLORS.get("warning", "#FFC107")
        tk.Label(
            header,
            text="✓ Válida" if obs.is_valid else "⚠ Revisar",
            font=FONTS["body_bold"], bg=quality_bg, fg=COLORS["text_inverse"],
            padx=SPACE_MD, pady=SPACE_SM // 2,
        ).pack(side="right", padx=SPACE_LG)

        # Body con scroll
        outer = tk.Frame(self, bg=COLORS["bg"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        container = tk.Frame(canvas, bg=COLORS["bg"])
        canvas.create_window((0, 0), window=container, anchor="nw", width=680)
        container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        body = tk.Frame(container, bg=COLORS["bg"])
        body.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        # Metadata
        self._render_section_header(body, "Metadata")
        self._render_kv(body, "ID de observación", str(obs.observation_id))
        self._render_kv(body, "Observado en UTC", obs.observed_at_utc.isoformat())
        self._render_kv(body, "Observado en local (AR)", obs.observed_at_local.isoformat())
        self._render_kv(body, "Cargado por (user_id)", str(obs.created_by_user_id))
        if obs.created_at_utc:
            self._render_kv(body, "Persistido en", obs.created_at_utc.isoformat())

        # Notas de calidad si hay
        if obs.validation_notes:
            self._render_section_header(body, "Notas de calidad")
            for flag in _parse_validation_flags(obs.validation_notes):
                label = _QUALITY_FLAG_LABELS.get(flag, flag)
                tk.Label(body, text=f"• {label}", font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(anchor="w")

        # Bloque cuantitativo
        self._render_section_header(body, "Mediciones cuantitativas")
        self._render_kv(body, "Lluvia (mm)", _fmt(obs.rain_mm))
        self._render_kv(body, "Temperatura (°C)", _fmt(obs.temp_c))
        beaufort_label = BEAUFORT_DESCRIPTIONS.get(obs.wind_beaufort) if obs.wind_beaufort is not None else None
        self._render_kv(body, "Viento (Beaufort)", beaufort_label or "—")
        self._render_kv(body, "Dirección viento", obs.wind_direction.value if obs.wind_direction else "—")
        self._render_kv(body, "Humedad percibida", obs.humidity_percept.value if obs.humidity_percept else "—")

        # Bloque cualitativo
        self._render_section_header(body, "Observaciones cualitativas")
        self._render_kv(body, "Cobertura cielo", f"{obs.sky_coverage_pct}%" if obs.sky_coverage_pct is not None else "—")
        self._render_kv(body, "Tipo de nubes", CLOUD_TYPE_DESCRIPTIONS.get(obs.cloud_type) if obs.cloud_type else "—")
        self._render_kv(body, "Estado del suelo", obs.soil_state.value if obs.soil_state else "—")
        self._render_kv(body, "Visibilidad", obs.visibility.value if obs.visibility else "—")
        self._render_kv(body, "Precipitación ahora", obs.precipitation_now.value if obs.precipitation_now else "—")

        # Texto libre
        if obs.phenology_notes or obs.livestock_state or obs.general_notes:
            self._render_section_header(body, "Observaciones del campo")
            if obs.phenology_notes:
                self._render_kv(body, "Fenología", obs.phenology_notes)
            if obs.livestock_state:
                lst = obs.livestock_state.value.capitalize()
                if obs.livestock_notes:
                    lst += f" · {obs.livestock_notes}"
                self._render_kv(body, "Ganado", lst)
            if obs.general_notes:
                self._render_kv(body, "Comentarios", obs.general_notes)

        # Eventos del mismo día
        if self._detail.events_same_day:
            self._render_section_header(body, f"Eventos puntuales del día ({len(self._detail.events_same_day)})")
            for evt in self._detail.events_same_day:
                self._render_event(body, evt)
        else:
            self._render_section_header(body, "Eventos puntuales del día")
            tk.Label(body, text="No se reportaron eventos puntuales este día.",
                     font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(anchor="w")

        # Footer
        footer = tk.Frame(self, bg=COLORS["bg_alt"], height=50)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        ttk.Button(footer, text="Cerrar", style="Secondary.TButton", command=self._close).pack(side="right", padx=SPACE_LG, pady=SPACE_SM)

    def _render_section_header(self, parent: tk.Misc, text: str) -> None:
        tk.Label(
            parent, text=text,
            font=FONTS["body_bold"], bg=COLORS["bg"], fg=COLORS["primary"],
        ).pack(anchor="w", pady=(SPACE_MD, SPACE_SM))

    def _render_kv(self, parent: tk.Misc, key: str, value: str) -> None:
        row = tk.Frame(parent, bg=COLORS["bg"])
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=f"{key}:", font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"], width=22, anchor="w").pack(side="left")
        tk.Label(row, text=value, font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text"], wraplength=440, justify="left").pack(side="left", padx=SPACE_SM)

    def _render_event(self, parent: tk.Misc, evt: EmpiricalEvent) -> None:
        frame = tk.LabelFrame(parent, text=evt.event_type.value.replace("_", " ").capitalize(),
                              bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        frame.pack(anchor="w", fill="x", pady=SPACE_SM)

        if evt.started_at_local or evt.ended_at_local:
            tk.Label(
                frame,
                text=f"Desde {evt.started_at_local or '—'} hasta {evt.ended_at_local or '—'}",
                font=FONTS["body"], bg=COLORS["bg"],
            ).pack(anchor="w")
        if evt.hail_size:
            tk.Label(frame, text=f"Tamaño granizo: {evt.hail_size.value}", font=FONTS["body"], bg=COLORS["bg"]).pack(anchor="w")
        if evt.description:
            tk.Label(frame, text=evt.description, font=FONTS["body"], bg=COLORS["bg"], wraplength=600, justify="left").pack(anchor="w")

    def _close(self) -> None:
        self.grab_release()
        self.destroy()


def _parse_validation_flags(notes: str) -> list[str]:
    """Parsea ``validation_notes`` formato ``missing:a,b; range:c_out``."""
    flags: list[str] = []
    parts = notes.split(";")
    for part in parts:
        part = part.strip()
        if ":" in part:
            _, values = part.split(":", 1)
            flags.extend(v.strip() for v in values.split(",") if v.strip())
    return flags


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
