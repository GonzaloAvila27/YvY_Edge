"""Wizard de carga de observación empírica · 4 pasos.

Mismo patrón que onboarding wizard (Fase 6): una sola tk.Frame con state
interno acumulado entre steps. ``_render_step()`` destruye el body y lo
reconstruye según ``self._current_step``.

Steps:
    1. Cabecera (fecha, hora local, observador auto-fill)
    2. Bloque A: cuantitativas (rain, temp, beaufort, dir, humedad)
    3. Bloque B: cualitativas (cielo, nubes, suelo, visibilidad, lluvia,
       fenología, ganado)
    4. Comentarios + eventos puntuales del día + revisión + confirmar
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from yvy.application.use_cases.empirical.create_empirical_observation import (
    CreateObservationInput,
    CreateObservationResult,
)
from yvy.domain.auth.models import User
from yvy.domain.empirical.enums import (
    BEAUFORT_DESCRIPTIONS,
    CLOUD_TYPE_DESCRIPTIONS,
    CloudType,
    HumidityPercept,
    LivestockState,
    PrecipitationNow,
    SoilState,
    Visibility,
    WindDirection,
)
from yvy.presentation.controllers.empirical_controller import (
    CreateObservationCallbacks,
    EmpiricalController,
)
from yvy.presentation.theme import COLORS, FONTS, SPACE_LG, SPACE_MD, SPACE_SM
from yvy.presentation.views.empirical.event_form_modal import EmpiricalEventFormModal

logger = logging.getLogger(__name__)

# Tz Argentina UTC-3
_TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

# Etiquetas legibles para reportar campos faltantes al usuario
_FIELD_LABELS_ES: dict[str, str] = {
    "temp_c": "temperatura",
    "rain_mm": "lluvia",
    "sky_coverage_pct": "cobertura del cielo",
    "wind_direction": "dirección del viento",
    "wind_beaufort": "intensidad del viento",
    "temp_c_out_of_range": "temperatura fuera de rango",
    "rain_mm_out_of_range": "lluvia fuera de rango",
}


class EmpiricalWizardView(tk.Frame):
    """Wizard de 4 pasos para cargar una observación empírica."""

    def __init__(
        self,
        parent: tk.Misc,
        controller: EmpiricalController,
        current_user: User,
        on_complete: callable,  # type: ignore[type-arg]
        on_cancel: callable,  # type: ignore[type-arg]
    ) -> None:
        super().__init__(parent, bg=COLORS["bg"])
        self._controller = controller
        self._current_user = current_user
        self._on_complete = on_complete
        self._on_cancel = on_cancel

        # State acumulado entre steps
        self._current_step = 0
        self._state: dict = {
            # Step 1
            "observed_date": datetime.now(_TZ_AR).date(),
            "observed_hour": datetime.now(_TZ_AR).hour,
            "observed_minute": datetime.now(_TZ_AR).minute,
            # Step 2
            "rain_mm": None,
            "temp_c": None,
            "wind_beaufort": None,
            "wind_direction": None,
            "humidity_percept": None,
            # Step 3
            "sky_coverage_pct": None,
            "cloud_type": None,
            "soil_state": None,
            "visibility": None,
            "precipitation_now": None,
            "phenology_notes": "",
            "livestock_state": None,
            "livestock_notes": "",
            # Step 4
            "general_notes": "",
            "events_added": [],  # lista de EmpiricalEvent ya guardados
        }

        self._build_layout()
        self._render_step()

    # ════════════════════════════════════════════════════════════════════
    # Layout base
    # ════════════════════════════════════════════════════════════════════

    def _build_layout(self) -> None:
        # Header con título + step indicator
        self._header = tk.Frame(self, bg=COLORS["primary"], height=60)
        self._header.pack(side="top", fill="x")
        self._header.pack_propagate(False)

        tk.Label(
            self._header,
            text="Carga de observación empírica",
            font=FONTS["heading"],
            bg=COLORS["primary"],
            fg=COLORS["text_inverse"],
        ).pack(side="left", padx=SPACE_LG)

        self._step_label = tk.Label(
            self._header, text="Paso 1 de 4",
            font=FONTS["body"], bg=COLORS["primary"], fg=COLORS["text_inverse"],
        )
        self._step_label.pack(side="right", padx=SPACE_LG)

        # Body (se reconstruye en cada step)
        self._body = tk.Frame(self, bg=COLORS["bg"])
        self._body.pack(side="top", fill="both", expand=True)

        # Footer fijo con navegación
        self._footer = tk.Frame(self, bg=COLORS["bg_alt"], height=60)
        self._footer.pack(side="bottom", fill="x")
        self._footer.pack_propagate(False)

        self._btn_cancel = ttk.Button(
            self._footer, text="Cancelar", style="Secondary.TButton",
            command=self._handle_cancel,
        )
        self._btn_cancel.pack(side="left", padx=SPACE_LG, pady=SPACE_MD)

        self._btn_back = ttk.Button(
            self._footer, text="Atrás", style="Secondary.TButton",
            command=self._go_back,
        )
        # se empaqueta dinámicamente en _render_step

        self._btn_next = ttk.Button(
            self._footer, text="Siguiente", style="Primary.TButton",
            command=self._go_next,
        )
        self._btn_next.pack(side="right", padx=SPACE_LG, pady=SPACE_MD)

    def _render_step(self) -> None:
        # Limpiar body
        for w in self._body.winfo_children():
            w.destroy()

        self._step_label.config(text=f"Paso {self._current_step + 1} de 4")

        # Botón Atrás visible desde step 2 en adelante
        if self._current_step == 0:
            self._btn_back.pack_forget()
        else:
            self._btn_back.pack(side="right", padx=SPACE_SM, pady=SPACE_MD)

        # Texto del botón Next
        if self._current_step == 3:
            self._btn_next.config(text="Guardar observación")
        else:
            self._btn_next.config(text="Siguiente")

        # Renderizar contenido según step
        if self._current_step == 0:
            self._render_step_header()
        elif self._current_step == 1:
            self._render_step_quantitative()
        elif self._current_step == 2:
            self._render_step_qualitative()
        elif self._current_step == 3:
            self._render_step_review()

    # ════════════════════════════════════════════════════════════════════
    # Step 1: Cabecera
    # ════════════════════════════════════════════════════════════════════

    def _render_step_header(self) -> None:
        container = tk.Frame(self._body, bg=COLORS["bg"])
        container.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            container,
            text="Cuándo y quién observa",
            font=FONTS["heading"], bg=COLORS["bg"], fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        tk.Label(
            container,
            text=("Indicá la fecha y hora del momento de observación.\n"
                  "Si estás cargando una observación retrospectiva, podés elegir hasta 7 días atrás."),
            font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"],
            justify="left", wraplength=600,
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Fecha (date picker simple con 3 spinbox)
        date_frame = tk.Frame(container, bg=COLORS["bg"])
        date_frame.pack(anchor="w", pady=SPACE_SM)
        tk.Label(date_frame, text="Fecha:", font=FONTS["body"], bg=COLORS["bg"]).pack(side="left")

        today = datetime.now(_TZ_AR).date()
        seven_days_ago = today - timedelta(days=7)

        d = self._state["observed_date"]
        self._day_var = tk.StringVar(value=f"{d.day:02d}")
        self._month_var = tk.StringVar(value=f"{d.month:02d}")
        self._year_var = tk.StringVar(value=f"{d.year}")

        ttk.Spinbox(date_frame, from_=1, to=31, textvariable=self._day_var, width=4).pack(side="left", padx=SPACE_SM)
        tk.Label(date_frame, text="/", bg=COLORS["bg"]).pack(side="left")
        ttk.Spinbox(date_frame, from_=1, to=12, textvariable=self._month_var, width=4).pack(side="left", padx=SPACE_SM)
        tk.Label(date_frame, text="/", bg=COLORS["bg"]).pack(side="left")
        ttk.Spinbox(date_frame, from_=seven_days_ago.year, to=today.year, textvariable=self._year_var, width=6).pack(side="left", padx=SPACE_SM)

        # Hora
        time_frame = tk.Frame(container, bg=COLORS["bg"])
        time_frame.pack(anchor="w", pady=SPACE_SM)
        tk.Label(time_frame, text="Hora:", font=FONTS["body"], bg=COLORS["bg"]).pack(side="left")
        self._hour_var = tk.StringVar(value=f"{self._state['observed_hour']:02d}")
        self._minute_var = tk.StringVar(value=f"{self._state['observed_minute']:02d}")
        ttk.Spinbox(time_frame, from_=0, to=23, textvariable=self._hour_var, width=4).pack(side="left", padx=SPACE_SM)
        tk.Label(time_frame, text=":", bg=COLORS["bg"]).pack(side="left")
        ttk.Spinbox(time_frame, from_=0, to=59, textvariable=self._minute_var, width=4).pack(side="left", padx=SPACE_SM)

        # Observador (read-only)
        obs_frame = tk.Frame(container, bg=COLORS["bg"])
        obs_frame.pack(anchor="w", pady=(SPACE_LG, 0))
        tk.Label(obs_frame, text="Observador:", font=FONTS["body"], bg=COLORS["bg"]).pack(side="left")
        tk.Label(
            obs_frame,
            text=f"{self._current_user.full_name} ({self._current_user.username})",
            font=FONTS["body_bold"], bg=COLORS["bg"], fg=COLORS["primary"],
        ).pack(side="left", padx=SPACE_SM)

    # ════════════════════════════════════════════════════════════════════
    # Step 2: Cuantitativas
    # ════════════════════════════════════════════════════════════════════

    def _render_step_quantitative(self) -> None:
        container = tk.Frame(self._body, bg=COLORS["bg"])
        container.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            container, text="Mediciones cuantitativas",
            font=FONTS["heading"], bg=COLORS["bg"], fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))
        tk.Label(
            container,
            text="Valores leídos de los instrumentos (pluviómetro, termómetro, etc).",
            font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Lluvia mm
        self._rain_var = tk.StringVar(value=str(self._state["rain_mm"] or ""))
        self._add_numeric_row(container, "Lluvia (mm):", self._rain_var, "Pluviómetro manual")

        # Temperatura
        self._temp_var = tk.StringVar(value=str(self._state["temp_c"] or ""))
        self._add_numeric_row(container, "Temperatura (°C):", self._temp_var, "Termómetro de máx/mín")

        # Beaufort
        beaufort_frame = tk.Frame(container, bg=COLORS["bg"])
        beaufort_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        tk.Label(beaufort_frame, text="Viento (Beaufort 0-12):", font=FONTS["body"], bg=COLORS["bg"], width=22, anchor="w").pack(side="left")
        self._beaufort_var = tk.StringVar(value=str(self._state["wind_beaufort"] or ""))
        beaufort_combo = ttk.Combobox(
            beaufort_frame,
            textvariable=self._beaufort_var,
            values=[""] + [BEAUFORT_DESCRIPTIONS[i] for i in range(0, 13)],
            state="readonly",
            width=50,
        )
        beaufort_combo.pack(side="left", padx=SPACE_SM)

        # Dirección viento (8 puntos cardinales como radio buttons)
        wind_dir_frame = tk.Frame(container, bg=COLORS["bg"])
        wind_dir_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        tk.Label(wind_dir_frame, text="Dirección viento:", font=FONTS["body"], bg=COLORS["bg"], width=22, anchor="w").pack(side="left")
        self._wind_dir_var = tk.StringVar(value=self._state["wind_direction"].value if self._state["wind_direction"] else "")
        for d in WindDirection:
            ttk.Radiobutton(
                wind_dir_frame, text=d.value, variable=self._wind_dir_var, value=d.value,
            ).pack(side="left", padx=2)

        # Humedad percibida
        hum_frame = tk.Frame(container, bg=COLORS["bg"])
        hum_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        tk.Label(hum_frame, text="Humedad percibida:", font=FONTS["body"], bg=COLORS["bg"], width=22, anchor="w").pack(side="left")
        self._humidity_var = tk.StringVar(value=self._state["humidity_percept"].value if self._state["humidity_percept"] else "")
        for h in HumidityPercept:
            ttk.Radiobutton(
                hum_frame, text=h.value.capitalize(), variable=self._humidity_var, value=h.value,
            ).pack(side="left", padx=SPACE_SM)

    def _add_numeric_row(
        self, parent: tk.Misc, label: str, var: tk.StringVar, hint: str
    ) -> None:
        """Helper para agregar una fila de input numérico con bloqueo de tipo."""
        row = tk.Frame(parent, bg=COLORS["bg"])
        row.pack(anchor="w", pady=SPACE_SM, fill="x")
        tk.Label(row, text=label, font=FONTS["body"], bg=COLORS["bg"], width=22, anchor="w").pack(side="left")

        # Bloqueo de tipo: solo permite dígitos, punto y signo menos
        vcmd = (self.register(_validate_numeric_input), "%P")
        entry = ttk.Entry(row, textvariable=var, validate="key", validatecommand=vcmd, width=12)
        entry.pack(side="left", padx=SPACE_SM)

        tk.Label(row, text=hint, font=FONTS["small"], bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(side="left")

    # ════════════════════════════════════════════════════════════════════
    # Step 3: Cualitativas
    # ════════════════════════════════════════════════════════════════════

    def _render_step_qualitative(self) -> None:
        # Scroll container para que no se corte en pantallas pequeñas
        outer = tk.Frame(self._body, bg=COLORS["bg"])
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        container = tk.Frame(canvas, bg=COLORS["bg"])
        canvas.create_window((0, 0), window=container, anchor="nw", width=900)
        container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        inner = tk.Frame(container, bg=COLORS["bg"])
        inner.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            inner, text="Observaciones a simple vista",
            font=FONTS["heading"], bg=COLORS["bg"], fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # Cobertura cielo (radio 5 valores)
        self._sky_var = tk.StringVar(value=str(self._state["sky_coverage_pct"]) if self._state["sky_coverage_pct"] is not None else "")
        sky_frame = tk.Frame(inner, bg=COLORS["bg"])
        sky_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        tk.Label(sky_frame, text="Cobertura del cielo:", font=FONTS["body_bold"], bg=COLORS["bg"]).pack(side="left", padx=(0, SPACE_MD))
        for pct in [0, 25, 50, 75, 100]:
            ttk.Radiobutton(sky_frame, text=f"{pct}%", variable=self._sky_var, value=str(pct)).pack(side="left", padx=SPACE_SM)

        # Tipo de nubes (radio 6 valores)
        self._cloud_var = tk.StringVar(value=self._state["cloud_type"].value if self._state["cloud_type"] else "")
        cloud_frame = tk.LabelFrame(inner, text="Tipo de nubes predominantes", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        cloud_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        for ct in CloudType:
            label = CLOUD_TYPE_DESCRIPTIONS[ct]
            ttk.Radiobutton(cloud_frame, text=label, variable=self._cloud_var, value=ct.value).pack(anchor="w")

        # Estado del suelo
        self._soil_var = tk.StringVar(value=self._state["soil_state"].value if self._state["soil_state"] else "")
        soil_frame = tk.LabelFrame(inner, text="Estado del suelo", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        soil_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        for s in SoilState:
            ttk.Radiobutton(soil_frame, text=s.value.capitalize(), variable=self._soil_var, value=s.value).pack(side="left", padx=SPACE_SM)

        # Visibilidad
        self._vis_var = tk.StringVar(value=self._state["visibility"].value if self._state["visibility"] else "")
        vis_frame = tk.LabelFrame(inner, text="Visibilidad", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        vis_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        for v in Visibility:
            ttk.Radiobutton(vis_frame, text=v.value.capitalize(), variable=self._vis_var, value=v.value).pack(side="left", padx=SPACE_SM)

        # Precipitación ahora
        self._precip_var = tk.StringVar(value=self._state["precipitation_now"].value if self._state["precipitation_now"] else "")
        precip_frame = tk.LabelFrame(inner, text="Precipitación al momento", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        precip_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        for p in PrecipitationNow:
            ttk.Radiobutton(precip_frame, text=p.value.replace("_", " ").capitalize(), variable=self._precip_var, value=p.value).pack(side="left", padx=SPACE_SM)

        # Fenología (textarea libre)
        tk.Label(inner, text="Fenología de cultivos (texto libre):", font=FONTS["body_bold"], bg=COLORS["bg"]).pack(anchor="w", pady=(SPACE_LG, SPACE_SM))
        self._phenology_text = tk.Text(inner, height=3, width=80, font=FONTS["body"])
        self._phenology_text.pack(anchor="w", fill="x")
        if self._state["phenology_notes"]:
            self._phenology_text.insert("1.0", self._state["phenology_notes"])

        # Ganado
        self._livestock_var = tk.StringVar(value=self._state["livestock_state"].value if self._state["livestock_state"] else "")
        livestock_frame = tk.LabelFrame(inner, text="Estado del ganado", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        livestock_frame.pack(anchor="w", pady=SPACE_SM, fill="x")
        for ls in LivestockState:
            ttk.Radiobutton(livestock_frame, text=ls.value.capitalize(), variable=self._livestock_var, value=ls.value).pack(side="left", padx=SPACE_SM)

        tk.Label(inner, text="Observaciones del ganado:", font=FONTS["body"], bg=COLORS["bg"]).pack(anchor="w", pady=(SPACE_SM, 0))
        self._livestock_notes_text = tk.Text(inner, height=2, width=80, font=FONTS["body"])
        self._livestock_notes_text.pack(anchor="w", fill="x")
        if self._state["livestock_notes"]:
            self._livestock_notes_text.insert("1.0", self._state["livestock_notes"])

    # ════════════════════════════════════════════════════════════════════
    # Step 4: Comentarios + eventos puntuales + revisión
    # ════════════════════════════════════════════════════════════════════

    def _render_step_review(self) -> None:
        container = tk.Frame(self._body, bg=COLORS["bg"])
        container.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            container, text="Comentarios generales y eventos puntuales",
            font=FONTS["heading"], bg=COLORS["bg"], fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # Comentarios generales
        tk.Label(container, text="Comentarios generales (opcional):", font=FONTS["body_bold"], bg=COLORS["bg"]).pack(anchor="w")
        self._general_notes_text = tk.Text(container, height=4, width=80, font=FONTS["body"])
        self._general_notes_text.pack(anchor="w", fill="x", pady=(SPACE_SM, SPACE_LG))
        if self._state["general_notes"]:
            self._general_notes_text.insert("1.0", self._state["general_notes"])

        # Eventos puntuales
        events_frame = tk.LabelFrame(
            container,
            text="Eventos puntuales del día (helada, granizo, viento fuerte, etc.)",
            bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM,
        )
        events_frame.pack(anchor="w", fill="x", pady=SPACE_SM)

        if not self._state["events_added"]:
            tk.Label(events_frame, text="No hay eventos puntuales cargados todavía.",
                     font=FONTS["body"], bg=COLORS["bg"], fg=COLORS["text_muted"]).pack(anchor="w")
        else:
            for evt in self._state["events_added"]:
                label = f"• {evt.event_type.value}"
                if evt.started_at_local:
                    label += f" desde {evt.started_at_local}"
                if evt.ended_at_local:
                    label += f" hasta {evt.ended_at_local}"
                tk.Label(events_frame, text=label, font=FONTS["body"], bg=COLORS["bg"]).pack(anchor="w")

        ttk.Button(
            events_frame, text="+ Agregar evento puntual",
            style="Secondary.TButton",
            command=self._open_event_modal,
        ).pack(anchor="w", pady=SPACE_SM)

        # Aviso de revisión
        tk.Label(
            container,
            text=("Al confirmar, la observación se guarda en YVY y se prepara para sincronizar con el servidor "
                  "cuando haya conexión. No se puede editar después; si te equivocaste, cargá una observación "
                  "nueva con los datos correctos."),
            font=FONTS["small"], bg=COLORS["bg"], fg=COLORS["text_muted"],
            wraplength=700, justify="left",
        ).pack(anchor="w", pady=(SPACE_LG, 0))

    # ════════════════════════════════════════════════════════════════════
    # Navegación
    # ════════════════════════════════════════════════════════════════════

    def _go_back(self) -> None:
        self._capture_current_step()
        if self._current_step > 0:
            self._current_step -= 1
            self._render_step()

    def _go_next(self) -> None:
        if not self._capture_current_step():
            return

        if self._current_step < 3:
            self._current_step += 1
            self._render_step()
        else:
            # Step 4: confirmar y guardar
            self._submit_observation()

    def _handle_cancel(self) -> None:
        if messagebox.askyesno(
            "Cancelar carga",
            "¿Cancelar la observación? Se perderán los datos cargados.",
        ):
            self._on_cancel()

    # ════════════════════════════════════════════════════════════════════
    # Captura de state de cada step (con validación)
    # ════════════════════════════════════════════════════════════════════

    def _capture_current_step(self) -> bool:
        """Captura los valores actuales al state. Devuelve False si hay error
        de formato que bloquea avance."""
        try:
            if self._current_step == 0:
                # Construir fecha
                try:
                    day = int(self._day_var.get())
                    month = int(self._month_var.get())
                    year = int(self._year_var.get())
                    self._state["observed_date"] = datetime(year, month, day).date()
                except ValueError as exc:
                    messagebox.showerror("Fecha inválida", f"Revisá la fecha: {exc}")
                    return False
                try:
                    self._state["observed_hour"] = int(self._hour_var.get())
                    self._state["observed_minute"] = int(self._minute_var.get())
                except ValueError:
                    messagebox.showerror("Hora inválida", "Hora y minutos deben ser números.")
                    return False

            elif self._current_step == 1:
                self._state["rain_mm"] = _parse_float_or_none(self._rain_var.get())
                self._state["temp_c"] = _parse_float_or_none(self._temp_var.get())
                # Beaufort viene del combo como "0 · Calma — ..."; tomamos el primer número
                bf_str = self._beaufort_var.get()
                self._state["wind_beaufort"] = int(bf_str.split(" ")[0]) if bf_str else None
                self._state["wind_direction"] = WindDirection(self._wind_dir_var.get()) if self._wind_dir_var.get() else None
                self._state["humidity_percept"] = HumidityPercept(self._humidity_var.get()) if self._humidity_var.get() else None

            elif self._current_step == 2:
                self._state["sky_coverage_pct"] = int(self._sky_var.get()) if self._sky_var.get() else None
                self._state["cloud_type"] = CloudType(self._cloud_var.get()) if self._cloud_var.get() else None
                self._state["soil_state"] = SoilState(self._soil_var.get()) if self._soil_var.get() else None
                self._state["visibility"] = Visibility(self._vis_var.get()) if self._vis_var.get() else None
                self._state["precipitation_now"] = PrecipitationNow(self._precip_var.get()) if self._precip_var.get() else None
                self._state["phenology_notes"] = self._phenology_text.get("1.0", "end").strip()
                self._state["livestock_state"] = LivestockState(self._livestock_var.get()) if self._livestock_var.get() else None
                self._state["livestock_notes"] = self._livestock_notes_text.get("1.0", "end").strip()

            elif self._current_step == 3:
                self._state["general_notes"] = self._general_notes_text.get("1.0", "end").strip()
        except Exception as exc:
            logger.exception("Error capturando step %d: %s", self._current_step, exc)
            messagebox.showerror("Error", f"Revisá los valores: {exc}")
            return False
        return True

    # ════════════════════════════════════════════════════════════════════
    # Submit final + modal de eventos
    # ════════════════════════════════════════════════════════════════════

    def _open_event_modal(self) -> None:
        """Abre el modal para agregar un evento puntual."""
        EmpiricalEventFormModal(
            parent=self,
            controller=self._controller,
            current_user=self._current_user,
            observation_date=self._state["observed_date"].isoformat(),
            observation_id=None,  # todavía no existe la observación
            on_created=self._on_event_added,
        )

    def _on_event_added(self, event) -> None:  # noqa: ANN001
        """Callback cuando se agrega un evento exitosamente."""
        self._state["events_added"].append(event)
        self._render_step()  # re-render para mostrar el evento

    def _submit_observation(self, with_confirmation: bool = False) -> None:
        """Construye el CreateObservationInput y lo envía al controller."""
        d = self._state["observed_date"]
        local_dt = datetime(
            d.year, d.month, d.day,
            self._state["observed_hour"], self._state["observed_minute"],
            tzinfo=_TZ_AR,
        )
        utc_dt = local_dt.astimezone(tz=ZoneInfo("UTC"))

        input_data = CreateObservationInput(
            observed_at_utc=utc_dt,
            observed_at_local=local_dt,
            actor=self._current_user,
            rain_mm=self._state["rain_mm"],
            temp_c=self._state["temp_c"],
            wind_beaufort=self._state["wind_beaufort"],
            wind_direction=self._state["wind_direction"],
            humidity_percept=self._state["humidity_percept"],
            sky_coverage_pct=self._state["sky_coverage_pct"],
            cloud_type=self._state["cloud_type"],
            soil_state=self._state["soil_state"],
            visibility=self._state["visibility"],
            precipitation_now=self._state["precipitation_now"],
            phenology_notes=self._state["phenology_notes"] or None,
            livestock_state=self._state["livestock_state"],
            livestock_notes=self._state["livestock_notes"] or None,
            general_notes=self._state["general_notes"] or None,
            confirmed_with_warnings=with_confirmation,
        )

        callbacks = CreateObservationCallbacks(
            on_success=lambda r: self.after(0, lambda: self._handle_success(r)),
            on_warnings=lambda r: self.after(0, lambda: self._handle_warnings(r)),
            on_validation_error=lambda msg: self.after(0, lambda: messagebox.showerror("Error de validación", msg)),
            on_unexpected_error=lambda e: self.after(0, lambda: messagebox.showerror("Error inesperado", str(e))),
        )

        self._controller.create_observation(input_data, callbacks)

    def _handle_success(self, result: CreateObservationResult) -> None:
        messagebox.showinfo(
            "Observación guardada",
            f"Observación cargada correctamente.\n"
            f"ID: {str(result.observation.observation_id)[:8]}...\n"
            f"Sync encolado: {'sí' if result.sync_enqueued else 'no'}",
        )
        self._on_complete()

    def _handle_warnings(self, result: CreateObservationResult) -> None:
        """Si hay warnings, pregunta confirmación y reenvía."""
        labels = [_FIELD_LABELS_ES.get(w, w) for w in result.quality_warnings]
        msg = "Atención:\n\n" + "\n".join(f"• {label}" for label in labels)
        msg += "\n\n¿Querés guardar la observación de todos modos?"
        if messagebox.askyesno("Datos faltantes o fuera de rango", msg):
            self._submit_observation(with_confirmation=True)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _validate_numeric_input(new_value: str) -> bool:
    """Validador de tk: permite vacío, dígitos, un punto y un signo menos inicial."""
    if new_value == "" or new_value == "-":
        return True
    try:
        float(new_value)
        return True
    except ValueError:
        return False


def _parse_float_or_none(s: str) -> float | None:
    s = s.strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None
