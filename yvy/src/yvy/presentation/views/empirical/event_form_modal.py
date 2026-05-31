"""Modal para cargar un evento puntual (helada/granizo/etc).

Se invoca desde el step 4 del wizard, o desde la list view en el futuro.
"""

from __future__ import annotations

import logging
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from yvy.application.use_cases.empirical.create_empirical_event import (
    CreateEventInput,
    CreateEventResult,
)
from yvy.domain.auth.models import User
from yvy.domain.empirical.enums import EventType, HailSize
from yvy.presentation.controllers.empirical_controller import (
    CreateEventCallbacks,
    EmpiricalController,
)
from yvy.presentation.theme import COLORS, FONTS, SPACE_LG, SPACE_MD, SPACE_SM

logger = logging.getLogger(__name__)

_TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")

_EVENT_LABELS: dict[EventType, str] = {
    EventType.HELADA: "Helada",
    EventType.GRANIZO: "Granizo",
    EventType.VIENTO_FUERTE: "Viento fuerte",
    EventType.LLUVIA_TORRENCIAL: "Lluvia torrencial",
    EventType.SEQUIA: "Sequía visible",
    EventType.NIEBLA_DENSA: "Niebla densa",
    EventType.TORMENTA_ELECTRICA: "Tormenta eléctrica",
}

_HAIL_SIZE_LABELS: dict[HailSize, str] = {
    HailSize.ARROZ: "Arroz (< 2mm)",
    HailSize.LENTEJA: "Lenteja (2-5mm)",
    HailSize.POROTO: "Poroto (5-10mm)",
    HailSize.CANICA: "Canica (10-20mm)",
    HailSize.NUEZ: "Nuez (> 20mm)",
}


class EmpiricalEventFormModal(tk.Toplevel):
    """Modal de carga de evento puntual.

    Pattern de modales del proyecto: overrideredirect off (queremos barra
    de título estándar con X), grab_set para modal real, posicionado relativo
    al parent.
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: EmpiricalController,
        current_user: User,
        observation_date: str,  # YYYY-MM-DD local
        observation_id,  # uuid.UUID | None
        on_created: callable,  # type: ignore[type-arg]
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._current_user = current_user
        self._observation_date = observation_date
        self._observation_id = observation_id
        self._on_created = on_created

        self.title("Cargar evento puntual")
        self.configure(bg=COLORS["bg"])
        self.geometry("500x550")
        self.transient(parent.winfo_toplevel())  # type: ignore[arg-type]
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build_layout()

    def _build_layout(self) -> None:
        # Header
        header = tk.Frame(self, bg=COLORS["primary"], height=50)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=f"Evento puntual del {self._observation_date}",
            font=FONTS["heading"], bg=COLORS["primary"], fg=COLORS["text_inverse"],
        ).pack(padx=SPACE_LG, pady=SPACE_SM, anchor="w")

        # Body
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(side="top", fill="both", expand=True, padx=SPACE_LG, pady=SPACE_LG)

        # Tipo de evento
        tk.Label(body, text="Tipo de evento:", font=FONTS["body_bold"], bg=COLORS["bg"]).pack(anchor="w", pady=(0, SPACE_SM))
        self._event_type_var = tk.StringVar()
        for et, label in _EVENT_LABELS.items():
            ttk.Radiobutton(body, text=label, variable=self._event_type_var, value=et.value, command=self._on_event_type_change).pack(anchor="w")

        # Hora inicio y fin (opcional)
        time_frame = tk.Frame(body, bg=COLORS["bg"])
        time_frame.pack(anchor="w", pady=SPACE_MD)
        tk.Label(time_frame, text="Hora inicio (HH:MM, opcional):", font=FONTS["body"], bg=COLORS["bg"]).pack(side="left")
        self._start_var = tk.StringVar()
        ttk.Entry(time_frame, textvariable=self._start_var, width=8).pack(side="left", padx=SPACE_SM)

        time_frame2 = tk.Frame(body, bg=COLORS["bg"])
        time_frame2.pack(anchor="w", pady=SPACE_SM)
        tk.Label(time_frame2, text="Hora fin (HH:MM, opcional):", font=FONTS["body"], bg=COLORS["bg"]).pack(side="left")
        self._end_var = tk.StringVar()
        ttk.Entry(time_frame2, textvariable=self._end_var, width=8).pack(side="left", padx=SPACE_SM)

        # Tamaño granizo (visible solo si event_type=GRANIZO)
        self._hail_frame = tk.LabelFrame(body, text="Tamaño del granizo", bg=COLORS["bg"], padx=SPACE_SM, pady=SPACE_SM)
        self._hail_size_var = tk.StringVar()
        for hs, label in _HAIL_SIZE_LABELS.items():
            ttk.Radiobutton(self._hail_frame, text=label, variable=self._hail_size_var, value=hs.value).pack(anchor="w")
        # No se empaqueta inicialmente

        # Descripción
        tk.Label(body, text="Descripción (opcional):", font=FONTS["body"], bg=COLORS["bg"]).pack(anchor="w", pady=(SPACE_MD, SPACE_SM))
        self._desc_text = tk.Text(body, height=3, font=FONTS["body"])
        self._desc_text.pack(fill="x")

        # Footer con botones
        footer = tk.Frame(self, bg=COLORS["bg_alt"], height=50)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        ttk.Button(footer, text="Cancelar", style="Secondary.TButton", command=self._close).pack(side="left", padx=SPACE_LG, pady=SPACE_SM)
        ttk.Button(footer, text="Guardar evento", style="Primary.TButton", command=self._save).pack(side="right", padx=SPACE_LG, pady=SPACE_SM)

    def _on_event_type_change(self) -> None:
        """Muestra/oculta el panel de tamaño granizo según event_type."""
        if self._event_type_var.get() == EventType.GRANIZO.value:
            self._hail_frame.pack(anchor="w", fill="x", pady=SPACE_SM, after=self._hail_frame.master.winfo_children()[6] if len(self._hail_frame.master.winfo_children()) > 6 else None)  # noqa: E501
        else:
            self._hail_frame.pack_forget()
            self._hail_size_var.set("")

    def _save(self) -> None:
        if not self._event_type_var.get():
            messagebox.showwarning("Falta tipo", "Seleccioná un tipo de evento.")
            return

        event_type = EventType(self._event_type_var.get())
        hail_size = None
        if event_type == EventType.GRANIZO and self._hail_size_var.get():
            hail_size = HailSize(self._hail_size_var.get())

        started = self._start_var.get().strip() or None
        ended = self._end_var.get().strip() or None
        description = self._desc_text.get("1.0", "end").strip() or None

        input_data = CreateEventInput(
            observation_date=self._observation_date,
            event_type=event_type,
            actor=self._current_user,
            observation_id=self._observation_id,
            started_at_local=started,
            ended_at_local=ended,
            hail_size=hail_size,
            description=description,
        )

        callbacks = CreateEventCallbacks(
            on_success=lambda r: self.after(0, lambda: self._handle_success(r)),
            on_validation_error=lambda msg: self.after(0, lambda: messagebox.showerror("Error de validación", msg)),
            on_unexpected_error=lambda e: self.after(0, lambda: messagebox.showerror("Error inesperado", str(e))),
        )

        self._controller.create_event(input_data, callbacks)

    def _handle_success(self, result: CreateEventResult) -> None:
        self._on_created(result.event)
        self._close()

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
