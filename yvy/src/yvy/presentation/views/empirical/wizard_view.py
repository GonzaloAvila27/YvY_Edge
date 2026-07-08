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
from yvy.presentation.components.help_button import HelpButton
from yvy.presentation.controllers.empirical_controller import (
    CreateObservationCallbacks,
    EmpiricalController,
)
from yvy.presentation.theme import (
    ACCENT_GOLD,
    BG_CARD,
    BORDER,
    COLORS,
    FONT_FORM_INPUT,
    FONT_FORM_LABEL,
    FONT_SMALL,
    FONTS,
    FORM_COL_GAP,
    FORM_LABEL_MB,
    FORM_PADDING_H,
    FORM_PADDING_V,
    FORM_ROW_GAP,
    FORM_TEXTAREA_HEIGHT,
    PRIMARY,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
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
        help_repository=None,  # type: ignore[no-untyped-def]
        on_open_help=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(parent, bg=COLORS["bg"])
        self._controller = controller
        self._current_user = current_user
        self._on_complete = on_complete
        self._on_cancel = on_cancel
        self._help_repo = help_repository
        self._on_open_help = on_open_help

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
            text="Cuaderno empírico",
            font=FONTS["heading"],
            bg=COLORS["primary"],
            fg=COLORS["text_inverse"],
        ).pack(side="left", padx=SPACE_LG)

        self._step_label = tk.Label(
            self._header,
            text="Paso 1 de 4",
            font=FONTS["body"],
            bg=COLORS["primary"],
            fg=COLORS["text_inverse"],
        )
        self._step_label.pack(side="right", padx=SPACE_LG)

        # Footer fijo con navegación — debe empaquetarse ANTES que body
        # para que pack(expand=True) del body no lo desplace
        self._footer = tk.Frame(self, bg=COLORS["bg_alt"], height=60)
        self._footer.pack(side="bottom", fill="x")
        self._footer.pack_propagate(False)

        # Body scrollable compartido: en notebooks chicas el contenido de
        # varios pasos supera el alto disponible. self._body es el frame
        # interno donde renderizan los steps (sin cambios en sus métodos).
        body_wrap = tk.Frame(self, bg=COLORS["bg"])
        body_wrap.pack(side="top", fill="both", expand=True)

        self._body_canvas = tk.Canvas(body_wrap, bg=COLORS["bg"], highlightthickness=0)
        body_scroll = ttk.Scrollbar(body_wrap, orient="vertical", command=self._body_canvas.yview)
        self._body_canvas.configure(yscrollcommand=body_scroll.set)
        body_scroll.pack(side="right", fill="y")
        self._body_canvas.pack(side="left", fill="both", expand=True)

        self._body = tk.Frame(self._body_canvas, bg=COLORS["bg"])
        self._body_win = self._body_canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body_canvas.bind(
            "<Configure>",
            lambda e: self._body_canvas.itemconfig(self._body_win, width=e.width),
        )
        self._body.bind(
            "<Configure>",
            lambda _: self._body_canvas.configure(scrollregion=self._body_canvas.bbox("all")),
        )
        # Rueda del mouse, scoped al área del wizard (bind/unbind por hover)
        body_wrap.bind(
            "<Enter>",
            lambda _: self._body_canvas.bind_all("<MouseWheel>", self._on_mousewheel),
        )
        body_wrap.bind("<Leave>", lambda _: self._body_canvas.unbind_all("<MouseWheel>"))

        self._btn_cancel = ttk.Button(
            self._footer,
            text="Cancelar",
            style="Secondary.TButton",
            command=self._handle_cancel,
        )
        self._btn_cancel.pack(side="left", padx=SPACE_LG, pady=SPACE_MD)

        self._btn_back = ttk.Button(
            self._footer,
            text="Atrás",
            style="Secondary.TButton",
            command=self._go_back,
        )
        # se empaqueta dinámicamente en _render_step

        self._btn_next = ttk.Button(
            self._footer,
            text="Siguiente",
            style="Primary.TButton",
            command=self._go_next,
        )
        self._btn_next.pack(side="right", padx=SPACE_LG, pady=SPACE_MD)

    def apply_theme(self, palette: dict) -> None:
        """Aplica la paleta dada a todos los widgets del wizard."""
        self._last_palette: dict | None = palette
        from yvy.presentation.theme_manager import recolor

        recolor(self, palette)

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

        # Re-aplicar tema si dark mode estaba activo antes del re-render
        lp = getattr(self, "_last_palette", None)
        if lp is not None:
            from yvy.presentation.theme_manager import recolor

            recolor(self._body, lp)

        # Cada step arranca desde el tope del scroll
        self._body_canvas.yview_moveto(0)
        self.after_idle(
            lambda: self._body_canvas.configure(scrollregion=self._body_canvas.bbox("all"))
        )

    def _on_mousewheel(self, event) -> None:
        """Scroll del body con la rueda del mouse (Windows: delta múltiplo de 120)."""
        self._body_canvas.yview_scroll(int(-event.delta / 120), "units")

    # ─── Ayuda contextual ([?] por campo) ─────────────────────────────────

    def _help_btn(self, parent, article_key):  # type: ignore[no-untyped-def]
        """HelpButton del campo, o None si no hay repo o el artículo no existe."""
        if self._help_repo is None:
            return None
        try:
            if self._help_repo.get_article(article_key) is None:
                return None
        except Exception:
            return None
        return HelpButton(
            parent,
            help_repository=self._help_repo,
            article_key=article_key,
            on_expand=self._on_open_help,
            bg=COLORS["bg"],
        )

    def _field_header(
        self,
        parent,
        text,
        article_key,
        *,
        font=FONT_FORM_LABEL,
        fg=TEXT_PRIMARY,
        pady=(0, FORM_LABEL_MB),
    ):  # type: ignore[no-untyped-def]
        """Fila 'label + [?]' para encabezar un campo. Reemplaza un tk.Label simple."""
        hdr = tk.Frame(parent, bg=COLORS["bg"])
        hdr.pack(anchor="w", pady=pady)
        tk.Label(
            hdr,
            text=text,
            font=font,
            bg=COLORS["bg"],
            fg=fg,
            anchor="w",
        ).pack(side="left")
        hb = self._help_btn(hdr, article_key)
        if hb is not None:
            hb.pack(side="left", padx=(6, 0))
        return hdr

    # ════════════════════════════════════════════════════════════════════
    # Step 1: Cabecera
    # ════════════════════════════════════════════════════════════════════

    def _render_step_header(self) -> None:
        container = tk.Frame(self._body, bg=COLORS["bg"])
        container.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            container,
            text="Cuándo y quién observa",
            font=FONTS["heading"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        tk.Label(
            container,
            text=(
                "Indicá la fecha y hora del momento de observación.\n"
                "Si estás cargando una observación retrospectiva, podés elegir hasta 7 días atrás."
            ),
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text_muted"],
            justify="left",
            wraplength=600,
        ).pack(anchor="w", pady=(0, SPACE_LG))

        # Grid de 2 columnas: etiqueta (col 0, ancho fijo) | inputs (col 1)
        form = tk.Frame(container, bg=COLORS["bg"])
        form.pack(anchor="w")
        # Col 0 ancho fijo → los inputs de todas las filas arrancan en la misma x
        form.columnconfigure(0, minsize=110)
        form.columnconfigure(1, weight=1)

        today = datetime.now(_TZ_AR).date()
        seven_days_ago = today - timedelta(days=7)
        d = self._state["observed_date"]
        self._day_var = tk.StringVar(value=f"{d.day:02d}")
        self._month_var = tk.StringVar(value=f"{d.month:02d}")
        self._year_var = tk.StringVar(value=f"{d.year}")

        # ── Fila 0: Fecha ─────────────────────────────────────────────────
        tk.Label(
            form,
            text="Fecha",
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
            anchor="e",
        ).grid(row=0, column=0, sticky="e", pady=SPACE_SM, padx=(0, SPACE_MD))

        date_inputs = tk.Frame(form, bg=COLORS["bg"])
        date_inputs.grid(row=0, column=1, sticky="w", pady=SPACE_SM)
        ttk.Spinbox(date_inputs, from_=1, to=31, textvariable=self._day_var, width=4).pack(
            side="left"
        )
        tk.Label(date_inputs, text="/", bg=COLORS["bg"], padx=SPACE_XS).pack(side="left")
        ttk.Spinbox(date_inputs, from_=1, to=12, textvariable=self._month_var, width=4).pack(
            side="left"
        )
        tk.Label(date_inputs, text="/", bg=COLORS["bg"], padx=SPACE_XS).pack(side="left")
        ttk.Spinbox(
            date_inputs,
            from_=seven_days_ago.year,
            to=today.year,
            textvariable=self._year_var,
            width=6,
        ).pack(side="left")

        # ── Fila 1: Hora ──────────────────────────────────────────────────
        tk.Label(
            form,
            text="Hora",
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
            anchor="e",
        ).grid(row=1, column=0, sticky="e", pady=SPACE_SM, padx=(0, SPACE_MD))

        self._hour_var = tk.StringVar(value=f"{self._state['observed_hour']:02d}")
        self._minute_var = tk.StringVar(value=f"{self._state['observed_minute']:02d}")

        time_inputs = tk.Frame(form, bg=COLORS["bg"])
        time_inputs.grid(row=1, column=1, sticky="w", pady=SPACE_SM)
        ttk.Spinbox(time_inputs, from_=0, to=23, textvariable=self._hour_var, width=4).pack(
            side="left"
        )
        tk.Label(time_inputs, text=":", bg=COLORS["bg"], padx=SPACE_XS).pack(side="left")
        ttk.Spinbox(time_inputs, from_=0, to=59, textvariable=self._minute_var, width=4).pack(
            side="left"
        )

        # ── Fila 2: Observador (read-only) ────────────────────────────────
        tk.Label(
            form,
            text="Observador",
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
            anchor="e",
        ).grid(row=2, column=0, sticky="e", pady=(SPACE_LG, 0), padx=(0, SPACE_MD))

        obs_value = tk.Frame(form, bg=COLORS["bg"])
        obs_value.grid(row=2, column=1, sticky="w", pady=(SPACE_LG, 0))
        tk.Label(
            obs_value,
            text=f"{self._current_user.full_name}",
            font=FONTS["body_bold"],
            bg=COLORS["bg"],
            fg=ACCENT_GOLD,
        ).pack(side="left")
        tk.Label(
            obs_value,
            text=f"({self._current_user.username})",
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text_muted"],
        ).pack(side="left", padx=(SPACE_SM, 0))

    # ════════════════════════════════════════════════════════════════════
    # Step 2: Cuantitativas
    # ════════════════════════════════════════════════════════════════════

    def _render_step_quantitative(self) -> None:
        """Step 2 — Mediciones cuantitativas.

        Grid de 2 columnas, label-above-input.

        Fila 0 (col 0 | col 1): Lluvia (mm) | Temperatura (°C)
        Fila 1 (span 2):        Viento Beaufort 0-12  [Combobox full-width]
        Fila 2 (span 2):        Dirección viento      [8 RadioButtons]
        Fila 3 (span 2):        Humedad percibida     [4 RadioButtons]
        """
        outer = tk.Frame(self._body, bg=COLORS["bg"])
        outer.pack(
            padx=FORM_PADDING_H,
            pady=FORM_PADDING_V,
            fill="both",
            expand=True,
        )

        tk.Label(
            outer,
            text="Mediciones cuantitativas",
            font=FONTS["heading"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))
        tk.Label(
            outer,
            text="Valores leídos de los instrumentos (pluviómetro, termómetro, etc).",
            font=FONTS["body"],
            bg=COLORS["bg"],
            fg=COLORS["text_muted"],
        ).pack(anchor="w", pady=(0, FORM_ROW_GAP))

        # ── Grid 2 columnas ─────────────────────────────────────────────
        grid = tk.Frame(outer, bg=COLORS["bg"])
        grid.pack(fill="x")
        # Columnas iguales con peso uniforme; "col" fuerza ancho idéntico
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        # ── Fila 0: Lluvia | Temperatura ────────────────────────────────
        half_gap = FORM_COL_GAP // 2
        self._rain_var = tk.StringVar(value=str(self._state["rain_mm"] or ""))
        self._temp_var = tk.StringVar(value=str(self._state["temp_c"] or ""))

        self._place_numeric_field(
            grid,
            row=0,
            col=0,
            label="Lluvia (mm)",
            var=self._rain_var,
            hint="Pluviómetro manual",
            padx=(0, half_gap),
            article_key="glosario_lluvia_uv",
        )
        self._place_numeric_field(
            grid,
            row=0,
            col=1,
            label="Temperatura (°C)",
            var=self._temp_var,
            hint="Termómetro de máx/mín",
            padx=(half_gap, 0),
            article_key="glosario_temperatura",
        )

        # ── Fila 1: Viento Beaufort (span 2, full-width) ─────────────────
        beau_cell = tk.Frame(grid, bg=COLORS["bg"])
        beau_cell.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(FORM_ROW_GAP, 0),
        )
        self._field_header(beau_cell, "Viento (Beaufort 0-12)", "glosario_beaufort")
        self._beaufort_var = tk.StringVar(value=str(self._state["wind_beaufort"] or ""))
        ttk.Combobox(
            beau_cell,
            textvariable=self._beaufort_var,
            values=[""] + [BEAUFORT_DESCRIPTIONS[i] for i in range(0, 13)],
            state="readonly",
        ).pack(fill="x")

        # ── Fila 2: Dirección viento — 8 radio buttons distribuidos ──────
        wind_cell = tk.Frame(grid, bg=COLORS["bg"])
        wind_cell.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(FORM_ROW_GAP, 0),
        )
        self._field_header(wind_cell, "Dirección del viento", "glosario_viento")

        radio_wind = tk.Frame(wind_cell, bg=COLORS["bg"])
        radio_wind.pack(fill="x")
        # Distribuir 8 puntos cardinales con columnas de peso uniforme
        # para que el espaciado sea proporcional al ancho disponible.
        for i, d in enumerate(WindDirection):
            radio_wind.columnconfigure(i, weight=1)
        self._wind_dir_var = tk.StringVar(
            value=self._state["wind_direction"].value if self._state["wind_direction"] else ""
        )
        for i, d in enumerate(WindDirection):
            ttk.Radiobutton(
                radio_wind,
                text=d.value,
                variable=self._wind_dir_var,
                value=d.value,
            ).grid(row=0, column=i, sticky="w", padx=12)

        # ── Fila 3: Humedad percibida — 4 radio buttons ───────────────────
        hum_cell = tk.Frame(grid, bg=COLORS["bg"])
        hum_cell.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(FORM_ROW_GAP, 0),
        )
        self._field_header(hum_cell, "Humedad percibida", "glosario_humedad")

        radio_hum = tk.Frame(hum_cell, bg=COLORS["bg"])
        radio_hum.pack(fill="x")
        self._humidity_var = tk.StringVar(
            value=self._state["humidity_percept"].value if self._state["humidity_percept"] else ""
        )
        for h in HumidityPercept:
            ttk.Radiobutton(
                radio_hum,
                text=h.value.capitalize(),
                variable=self._humidity_var,
                value=h.value,
            ).pack(side="left", padx=FORM_COL_GAP)

    def _place_numeric_field(
        self,
        parent: tk.Misc,
        row: int,
        col: int,
        label: str,
        var: tk.StringVar,
        hint: str,
        padx: tuple[int, int] = (0, 0),
        article_key: str | None = None,
    ) -> None:
        """Celda de grid: label (+[?] opcional) arriba, Entry, hint abajo."""
        cell = tk.Frame(parent, bg=COLORS["bg"])
        cell.grid(row=row, column=col, sticky="nsew", padx=padx)

        if article_key is not None:
            self._field_header(cell, label, article_key)
        else:
            tk.Label(
                cell,
                text=label,
                font=FONT_FORM_LABEL,
                bg=COLORS["bg"],
                fg=TEXT_PRIMARY,
                anchor="w",
            ).pack(anchor="w", pady=(0, FORM_LABEL_MB))

        vcmd = (self.register(_validate_numeric_input), "%P")
        tk.Entry(
            cell,
            textvariable=var,
            validate="key",
            validatecommand=vcmd,
            font=FONT_FORM_INPUT,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            highlightcolor=PRIMARY,
        ).pack(fill="x", ipady=7)  # ipady=7 → altura ≈ FORM_INPUT_HEIGHT (34px)

        tk.Label(
            cell,
            text=hint,
            font=FONT_SMALL,
            bg=COLORS["bg"],
            fg=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w", pady=(FORM_LABEL_MB, 0))

    # ════════════════════════════════════════════════════════════════════
    # Step 3: Cualitativas
    # ════════════════════════════════════════════════════════════════════

    def _render_step_qualitative(self) -> None:
        """Step 3 — Observaciones a simple vista.

        Grid de 2 columnas. El scroll lo provee el body compartido
        (self._body dentro del canvas del wizard); este step solo renderiza
        su contenido, sin canvas propio.

        Fila 0 (span 2): Cobertura del cielo — 5 radios en línea
        Fila 1 col 0:    LabelFrame Tipo de nubes (6 radios verticales)
        Fila 1 col 1:    Suelo + Visibilidad + Precipitación apilados
        Fila 2 (span 2): Fenología — Text FORM_TEXTAREA_HEIGHT
        Fila 3 col 0:    LabelFrame Estado del ganado (4 radios horiz)
        Fila 3 col 1:    Observaciones del ganado — Text
        """
        inner = tk.Frame(self._body, bg=COLORS["bg"])
        inner.pack(padx=FORM_PADDING_H, pady=FORM_PADDING_V, fill="both", expand=True)

        tk.Label(
            inner,
            text="Observaciones a simple vista",
            font=FONTS["heading"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # ── Grid 2 columnas ──────────────────────────────────────────────
        grid = tk.Frame(inner, bg=COLORS["bg"])
        grid.pack(fill="both", expand=True)
        # uniform="col" garantiza columnas de ancho idéntico aunque el
        # LabelFrame de nubes tenga opciones más largas que la derecha.
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        half_gap = FORM_COL_GAP // 2
        _rg = FORM_ROW_GAP  # alias local para legibilidad

        # ── Fila 0: Cobertura del cielo (span 2, radios en línea) ────────
        self._sky_var = tk.StringVar(
            value=str(self._state["sky_coverage_pct"])
            if self._state["sky_coverage_pct"] is not None
            else ""
        )
        sky_cell = tk.Frame(grid, bg=COLORS["bg"])
        sky_cell.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, _rg))

        self._field_header(sky_cell, "Cobertura del cielo", "glosario_cobertura_cielo")

        sky_radios = tk.Frame(sky_cell, bg=COLORS["bg"])
        sky_radios.pack(anchor="w")
        for pct in [0, 25, 50, 75, 100]:
            ttk.Radiobutton(
                sky_radios,
                text=f"{pct}%",
                variable=self._sky_var,
                value=str(pct),
            ).pack(side="left", padx=FORM_COL_GAP)

        # ── Fila 1 col 0: Tipo de nubes — 6 radios verticales ────────────
        self._cloud_var = tk.StringVar(
            value=self._state["cloud_type"].value if self._state["cloud_type"] else ""
        )
        cloud_lf = tk.LabelFrame(
            grid,
            text="Tipo de nubes predominantes",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        cloud_lf.grid(row=1, column=0, sticky="nsew", padx=(0, half_gap), pady=(0, _rg))
        # El título de un LabelFrame no admite widgets → [?] adentro, arriba.
        _cloud_help = self._help_btn(cloud_lf, "glosario_nubes")
        if _cloud_help is not None:
            _cloud_help.pack(anchor="e")
        for ct in CloudType:
            ttk.Radiobutton(
                cloud_lf,
                text=CLOUD_TYPE_DESCRIPTIONS[ct],
                variable=self._cloud_var,
                value=ct.value,
            ).pack(anchor="w", pady=2)

        # ── Fila 1 col 1: Suelo + Visibilidad + Precipitación apilados ───
        right_col = tk.Frame(grid, bg=COLORS["bg"])
        right_col.grid(row=1, column=1, sticky="nsew", padx=(half_gap, 0), pady=(0, _rg))

        self._soil_var = tk.StringVar(
            value=self._state["soil_state"].value if self._state["soil_state"] else ""
        )
        soil_lf = tk.LabelFrame(
            right_col,
            text="Estado del suelo",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        soil_lf.pack(fill="x", pady=(0, SPACE_SM))
        for s in SoilState:
            ttk.Radiobutton(
                soil_lf,
                text=s.value.capitalize(),
                variable=self._soil_var,
                value=s.value,
            ).pack(side="left", padx=SPACE_SM)

        self._vis_var = tk.StringVar(
            value=self._state["visibility"].value if self._state["visibility"] else ""
        )
        vis_lf = tk.LabelFrame(
            right_col,
            text="Visibilidad",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        vis_lf.pack(fill="x", pady=(0, SPACE_SM))
        for v in Visibility:
            ttk.Radiobutton(
                vis_lf,
                text=v.value.capitalize(),
                variable=self._vis_var,
                value=v.value,
            ).pack(side="left", padx=SPACE_SM)

        self._precip_var = tk.StringVar(
            value=self._state["precipitation_now"].value if self._state["precipitation_now"] else ""
        )
        precip_lf = tk.LabelFrame(
            right_col,
            text="Precipitación al momento",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        precip_lf.pack(fill="x")
        for p in PrecipitationNow:
            ttk.Radiobutton(
                precip_lf,
                text=p.value.replace("_", " ").capitalize(),
                variable=self._precip_var,
                value=p.value,
            ).pack(side="left", padx=SPACE_SM)

        # ── Fila 2: Fenología (span 2) ────────────────────────────────────
        pheno_cell = tk.Frame(grid, bg=COLORS["bg"])
        pheno_cell.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, _rg))

        tk.Label(
            pheno_cell,
            text="Fenología de cultivos (texto libre):",
            font=FONT_FORM_LABEL,
            bg=COLORS["bg"],
            fg=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, FORM_LABEL_MB))

        # Altura en líneas: FORM_TEXTAREA_HEIGHT / altura_línea_aprox
        _textarea_rows = max(3, FORM_TEXTAREA_HEIGHT // 20)
        self._phenology_text = tk.Text(
            pheno_cell,
            height=_textarea_rows,
            font=FONTS["body"],
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            highlightcolor=PRIMARY,
        )
        self._phenology_text.pack(fill="x")
        if self._state["phenology_notes"]:
            self._phenology_text.insert("1.0", self._state["phenology_notes"])

        # ── Fila 3 col 0: Estado del ganado — 4 radios horizontales ───────
        self._livestock_var = tk.StringVar(
            value=self._state["livestock_state"].value if self._state["livestock_state"] else ""
        )
        livestock_lf = tk.LabelFrame(
            grid,
            text="Estado del ganado",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        livestock_lf.grid(row=3, column=0, sticky="nsew", padx=(0, half_gap))
        for ls in LivestockState:
            ttk.Radiobutton(
                livestock_lf,
                text=ls.value.capitalize(),
                variable=self._livestock_var,
                value=ls.value,
            ).pack(side="left", padx=SPACE_SM)

        # ── Fila 3 col 1: Observaciones del ganado ────────────────────────
        notes_cell = tk.Frame(grid, bg=COLORS["bg"])
        notes_cell.grid(row=3, column=1, sticky="nsew", padx=(half_gap, 0))

        tk.Label(
            notes_cell,
            text="Observaciones del ganado:",
            font=FONT_FORM_LABEL,
            bg=COLORS["bg"],
            fg=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w", pady=(0, FORM_LABEL_MB))
        self._livestock_notes_text = tk.Text(
            notes_cell,
            height=3,
            font=FONTS["body"],
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            highlightcolor=PRIMARY,
        )
        self._livestock_notes_text.pack(fill="x", expand=True)
        if self._state["livestock_notes"]:
            self._livestock_notes_text.insert("1.0", self._state["livestock_notes"])

    # ════════════════════════════════════════════════════════════════════
    # Step 4: Comentarios + eventos puntuales + revisión
    # ════════════════════════════════════════════════════════════════════

    def _render_step_review(self) -> None:
        container = tk.Frame(self._body, bg=COLORS["bg"])
        container.pack(padx=SPACE_LG, pady=SPACE_LG, fill="both", expand=True)

        tk.Label(
            container,
            text="Comentarios generales y eventos puntuales",
            font=FONTS["heading"],
            bg=COLORS["bg"],
            fg=COLORS["text"],
        ).pack(anchor="w", pady=(0, SPACE_MD))

        # Comentarios generales
        tk.Label(
            container,
            text="Comentarios generales (opcional):",
            font=FONTS["body_bold"],
            bg=COLORS["bg"],
        ).pack(anchor="w")
        # bg/fg explícitos: sin ellos, en dark mode recolor() pinta el fg claro
        # pero la caja queda blanca (no reconoce "white"/SystemWindow) → texto
        # invisible. Mismo styling que los Text del step 3.
        self._general_notes_text = tk.Text(
            container,
            height=4,
            font=FONTS["body"],
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            highlightcolor=PRIMARY,
            insertbackground=TEXT_PRIMARY,
        )
        self._general_notes_text.pack(anchor="w", fill="x", pady=(SPACE_SM, SPACE_LG))
        if self._state["general_notes"]:
            self._general_notes_text.insert("1.0", self._state["general_notes"])

        # Eventos puntuales
        events_frame = tk.LabelFrame(
            container,
            text="Eventos puntuales del día (helada, granizo, viento fuerte, etc.)",
            bg=COLORS["bg"],
            padx=SPACE_SM,
            pady=SPACE_SM,
        )
        events_frame.pack(anchor="w", fill="x", pady=SPACE_SM)

        if not self._state["events_added"]:
            tk.Label(
                events_frame,
                text="No hay eventos puntuales cargados todavía.",
                font=FONTS["body"],
                bg=COLORS["bg"],
                fg=COLORS["text_muted"],
            ).pack(anchor="w")
        else:
            for evt in self._state["events_added"]:
                label = f"• {evt.event_type.value}"
                if evt.started_at_local:
                    label += f" desde {evt.started_at_local}"
                if evt.ended_at_local:
                    label += f" hasta {evt.ended_at_local}"
                tk.Label(events_frame, text=label, font=FONTS["body"], bg=COLORS["bg"]).pack(
                    anchor="w"
                )

        ttk.Button(
            events_frame,
            text="+ Agregar evento puntual",
            style="Secondary.TButton",
            command=self._open_event_modal,
        ).pack(anchor="w", pady=SPACE_SM)

        # Aviso de revisión
        tk.Label(
            container,
            text=(
                "Al confirmar, la observación se guarda en YVY y se prepara para sincronizar con el servidor "
                "cuando haya conexión. No se puede editar después; si te equivocaste, cargá una observación "
                "nueva con los datos correctos."
            ),
            font=FONTS["small"],
            bg=COLORS["bg"],
            fg=COLORS["text_muted"],
            wraplength=700,
            justify="left",
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
                self._state["wind_direction"] = (
                    WindDirection(self._wind_dir_var.get()) if self._wind_dir_var.get() else None
                )
                self._state["humidity_percept"] = (
                    HumidityPercept(self._humidity_var.get()) if self._humidity_var.get() else None
                )

            elif self._current_step == 2:
                self._state["sky_coverage_pct"] = (
                    int(self._sky_var.get()) if self._sky_var.get() else None
                )
                self._state["cloud_type"] = (
                    CloudType(self._cloud_var.get()) if self._cloud_var.get() else None
                )
                self._state["soil_state"] = (
                    SoilState(self._soil_var.get()) if self._soil_var.get() else None
                )
                self._state["visibility"] = (
                    Visibility(self._vis_var.get()) if self._vis_var.get() else None
                )
                self._state["precipitation_now"] = (
                    PrecipitationNow(self._precip_var.get()) if self._precip_var.get() else None
                )
                self._state["phenology_notes"] = self._phenology_text.get("1.0", "end").strip()
                self._state["livestock_state"] = (
                    LivestockState(self._livestock_var.get()) if self._livestock_var.get() else None
                )
                self._state["livestock_notes"] = self._livestock_notes_text.get(
                    "1.0", "end"
                ).strip()

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

    def _on_event_added(self, event) -> None:
        """Callback cuando se agrega un evento exitosamente."""
        self._capture_current_step()  # preservar general_notes antes de re-render
        self._state["events_added"].append(event)
        self._render_step()

    def _submit_observation(self, with_confirmation: bool = False) -> None:
        """Construye el CreateObservationInput y lo envía al controller."""
        d = self._state["observed_date"]
        local_dt = datetime(
            d.year,
            d.month,
            d.day,
            self._state["observed_hour"],
            self._state["observed_minute"],
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
            on_validation_error=lambda msg: self.after(
                0, lambda: messagebox.showerror("Error de validación", msg)
            ),
            on_unexpected_error=lambda e: self.after(
                0, lambda: messagebox.showerror("Error inesperado", str(e))
            ),
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
        """Resuelve los warnings de calidad.

        Distingue dos clases:
        - Valores FUERA DE RANGO (temp/lluvia): se bloquea el guardado. El
          observador debe corregir con un valor plausible o dejar el campo
          vacío si no lo conoce. No se registran valores físicamente absurdos.
        - Campos críticos FALTANTES: no invalidan la carga; se ofrece guardar
          de todos modos (la observación queda completa-parcial pero válida).
        """
        range_warnings = [w for w in result.quality_warnings if w.endswith("_out_of_range")]
        missing_warnings = [w for w in result.quality_warnings if not w.endswith("_out_of_range")]

        # 1) Fuera de rango → bloquear, guiar a corregir o dejar vacío
        if range_warnings:
            labels = [_FIELD_LABELS_ES.get(w, w) for w in range_warnings]
            msg = (
                "Estos valores están fuera de rango y no se pueden registrar:\n\n"
                + "\n".join(f"• {label}" for label in labels)
                + "\n\nCorregilos con un valor plausible. Si no conocés el valor "
                "real, dejá el campo vacío."
            )
            messagebox.showwarning("Valores fuera de rango", msg)
            return  # no se guarda; el observador vuelve a editar

        # 2) Solo faltan campos críticos → permitir guardar igual
        if missing_warnings:
            labels = [_FIELD_LABELS_ES.get(w, w) for w in missing_warnings]
            msg = "Faltan algunos datos:\n\n" + "\n".join(f"• {label}" for label in labels)
            msg += "\n\n¿Querés guardar la observación de todos modos?"
            if messagebox.askyesno("Datos faltantes", msg):
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
