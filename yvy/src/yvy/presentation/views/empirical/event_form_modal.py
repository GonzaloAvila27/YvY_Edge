"""Modal para cargar un evento puntual (helada/granizo/etc).

Se invoca desde el step 4 del wizard, o desde la list view en el futuro.
"""

from __future__ import annotations

import logging
import tkinter as tk
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
from yvy.presentation.theme import FONTS, SPACE_LG, SPACE_MD, SPACE_SM
from yvy.presentation.theme_manager import theme_manager

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

        # Paleta viva: los widgets tk clásicos (frames/labels/Text) deben
        # construirse con el tema activo. Los ttk se teman por estilo global.
        self._p = theme_manager.palette

        self.title("Cargar evento puntual")
        self.configure(bg=self._p["bg"])
        self.geometry("500x550")
        self.transient(parent.winfo_toplevel())  # type: ignore[arg-type]
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build_layout()

    def _build_layout(self) -> None:
        p = self._p
        # Header
        header = tk.Frame(self, bg=p["header"], height=50)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=f"Evento puntual del {self._observation_date}",
            font=FONTS["heading"], bg=p["header"], fg=p["text_on_dark"],
        ).pack(padx=SPACE_LG, pady=SPACE_SM, anchor="w")

        # Footer con botones — empaquetado ANTES que el body para que el
        # body (expand=True) no lo empuje fuera de pantalla en notebooks chicas.
        footer = tk.Frame(self, bg=p["sidebar"], height=50)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        ttk.Button(footer, text="Cancelar", style="Secondary.TButton", command=self._close).pack(side="left", padx=SPACE_LG, pady=SPACE_SM)
        ttk.Button(footer, text="Guardar evento", style="Primary.TButton", command=self._save).pack(side="right", padx=SPACE_LG, pady=SPACE_SM)

        # Body scrollable (en pantallas chicas el contenido supera los 550px)
        outer = tk.Frame(self, bg=p["bg"])
        outer.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=p["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=p["bg"])
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        inner = tk.Frame(body, bg=p["bg"], padx=SPACE_LG, pady=SPACE_LG)
        inner.pack(fill="both", expand=True)
        body = inner  # el resto del layout cuelga del inner

        # Tipo de evento
        tk.Label(body, text="Tipo de evento:", font=FONTS["body_bold"], bg=p["bg"], fg=p["text"]).pack(anchor="w", pady=(0, SPACE_SM))
        self._event_type_var = tk.StringVar()
        for et, label in _EVENT_LABELS.items():
            ttk.Radiobutton(body, text=label, variable=self._event_type_var, value=et.value, command=self._on_event_type_change).pack(anchor="w")

        # Hora inicio y fin (opcional)
        time_frame = tk.Frame(body, bg=p["bg"])
        time_frame.pack(anchor="w", pady=SPACE_MD)
        tk.Label(time_frame, text="Hora inicio (HH:MM, opcional):", font=FONTS["body"], bg=p["bg"], fg=p["text"]).pack(side="left")
        self._start_var = tk.StringVar()
        ttk.Entry(time_frame, textvariable=self._start_var, width=8).pack(side="left", padx=SPACE_SM)

        time_frame2 = tk.Frame(body, bg=p["bg"])
        time_frame2.pack(anchor="w", pady=SPACE_SM)
        tk.Label(time_frame2, text="Hora fin (HH:MM, opcional):", font=FONTS["body"], bg=p["bg"], fg=p["text"]).pack(side="left")
        self._end_var = tk.StringVar()
        ttk.Entry(time_frame2, textvariable=self._end_var, width=8).pack(side="left", padx=SPACE_SM)

        # Tamaño granizo (visible solo si event_type=GRANIZO)
        self._hail_frame = tk.LabelFrame(body, text="Tamaño del granizo", bg=p["bg"], fg=p["text"], padx=SPACE_SM, pady=SPACE_SM)
        self._hail_size_var = tk.StringVar()
        for hs, label in _HAIL_SIZE_LABELS.items():
            ttk.Radiobutton(self._hail_frame, text=label, variable=self._hail_size_var, value=hs.value).pack(anchor="w")
        # No se empaqueta inicialmente

        # Descripción
        self._desc_label = tk.Label(body, text="Descripción (opcional):", font=FONTS["body"], bg=p["bg"], fg=p["text"])
        self._desc_label.pack(anchor="w", pady=(SPACE_MD, SPACE_SM))
        self._desc_text = tk.Text(
            body, height=3, font=FONTS["body"],
            bg=p["surface"], fg=p["text"], relief="flat", bd=0,
            highlightbackground=p["border"], highlightthickness=1,
            insertbackground=p["text"],
        )
        self._desc_text.pack(fill="x")

    def _on_event_type_change(self) -> None:
        """Muestra/oculta el panel de tamaño granizo según event_type."""
        if self._event_type_var.get() == EventType.GRANIZO.value:
            # Posicionar justo antes de la descripción (robusto al orden de hijos).
            self._hail_frame.pack(
                anchor="w", fill="x", pady=SPACE_SM, before=self._desc_label,
            )
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
