"""Header superior: barra de 60px con identidad institucional y controles.

Implementación: tk clásico (no ttk). Razón: el header tiene fondo azul
profundo (#1E3A5F) y todos los hijos viven sobre ese fondo. En ttk con
clam, forzar bg en cada widget hijo via styles nombrados es factible
pero frágil; con tk clásico se hereda bg directo y tenemos control total.

Layout (de izquierda a derecha):
    [Logo YVY 200px] [Identidad IEA flex] [4 indicadores] [Bell] [Avatar]

Estados de los 4 indicadores manipulables via métodos públicos:
    set_sensor_status(state, tooltip)
    set_sync_status(state, tooltip)
    set_ntp_status(state, tooltip)
    set_connectivity_status(state, tooltip)

Avatar:
    - Círculo simulado con Canvas (32x32).
    - Color de fondo según rol.
    - Iniciales blancas en el centro.
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable

from yvy.presentation.components.status_indicator import State, StatusIndicator
from yvy.presentation.theme import (
    ACCENT_GOLD,
    ACCENT_OLIVE,
    FONT_BODY_BOLD,
    FONT_LOGO,
    FONT_SMALL,
    FONT_TINY,
    HEADER_HEIGHT,
    PRIMARY,
    PRIMARY_LIGHT,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_ON_DARK,
    TEXT_ON_DARK_MUTED,
    role_color,
)

logger = logging.getLogger(__name__)


class Header(tk.Frame):
    """Barra superior de la app autenticada.

    Args:
        parent: widget padre (típicamente la ventana principal).
        iea_name: nombre de la institución (ej. "IEA Nº10 — Posadas").
        iea_cue: código CUE de la institución (ej. "540178700").
        user_name: nombre completo del usuario logueado.
        user_role: uno de superadmin/admin/profesor/alumno.
        on_notifications_click: callback al click en la campana.
        on_avatar_click: callback al click en el avatar.
        notifications_count: cantidad inicial de notificaciones (badge).
    """

    def __init__(
        self,
        parent: tk.Misc,
        iea_name: str,
        iea_cue: str,
        user_name: str,
        user_role: str,
        on_notifications_click: Callable[[], None] | None = None,
        on_avatar_click: Callable[[], None] | None = None,
        notifications_count: int = 0,
    ) -> None:
        super().__init__(parent, bg=PRIMARY, height=HEADER_HEIGHT)
        self.pack_propagate(False)

        self._user_role = user_role.lower()
        self._on_notif_click = on_notifications_click
        self._on_avatar_click = on_avatar_click

        self._build_logo()
        self._build_identity(iea_name, iea_cue)
        self._build_indicators()
        self._build_notifications(notifications_count)
        self._build_avatar(user_name, user_role)

    # ─── Subsecciones ────────────────────────────────────────────────────

    def _build_logo(self) -> None:
        """Logo YVY a la izquierda. Por ahora texto; PNG después."""
        logo_frame = tk.Frame(self, bg=PRIMARY, width=200)
        logo_frame.pack(side="left", fill="y", padx=(SPACE_XL, 0))
        logo_frame.pack_propagate(False)

        logo_label = tk.Label(
            logo_frame,
            text="YVY",
            bg=PRIMARY,
            fg=SUCCESS,  # oliva luz
            font=FONT_LOGO,
            anchor="w",
        )
        logo_label.pack(fill="both", expand=True, side="left")

    def _build_identity(self, iea_name: str, iea_cue: str) -> None:
        """Nombre IEA + CUE en el centro."""
        identity = tk.Frame(self, bg=PRIMARY)
        identity.pack(side="left", fill="y", padx=(SPACE_XL, 0))

        # Centramos verticalmente con un wrapper
        inner = tk.Frame(identity, bg=PRIMARY)
        inner.pack(expand=True, fill="y")

        name_label = tk.Label(
            inner,
            text=iea_name,
            bg=PRIMARY,
            fg=TEXT_ON_DARK,
            font=FONT_BODY_BOLD,
            anchor="w",
        )
        name_label.pack(anchor="w", pady=(SPACE_SM + 2, 0))

        cue_label = tk.Label(
            inner,
            text=f"CUE: {iea_cue}",
            bg=PRIMARY,
            fg=TEXT_ON_DARK_MUTED,
            font=FONT_TINY,
            anchor="w",
        )
        cue_label.pack(anchor="w")

    def _build_indicators(self) -> None:
        """4 status indicators: sensor, sync, NTP, conectividad."""
        ind_frame = tk.Frame(self, bg=PRIMARY)
        ind_frame.pack(side="left", padx=SPACE_XL, fill="y")

        inner = tk.Frame(ind_frame, bg=PRIMARY)
        inner.pack(expand=True)

        self._sensor_ind = StatusIndicator(
            inner,
            icon_key="radio",
            label="Sensor",
            state="neutral",
            tooltip="Sensor: estado desconocido",
            bg=PRIMARY,
            on_dark=True,
        )
        self._sensor_ind.pack(side="left", padx=SPACE_SM)

        self._sync_ind = StatusIndicator(
            inner,
            icon_key="refresh",
            label="Sync",
            state="neutral",
            tooltip="Sync: estado desconocido",
            bg=PRIMARY,
            on_dark=True,
        )
        self._sync_ind.pack(side="left", padx=SPACE_SM)

        self._ntp_ind = StatusIndicator(
            inner,
            icon_key="clock",
            label="NTP",
            state="neutral",
            tooltip="NTP: estado desconocido",
            bg=PRIMARY,
            on_dark=True,
        )
        self._ntp_ind.pack(side="left", padx=SPACE_SM)

        self._conn_ind = StatusIndicator(
            inner,
            icon_key="wifi",
            label="Online",
            state="neutral",
            tooltip="Conectividad: estado desconocido",
            bg=PRIMARY,
            on_dark=True,
        )
        self._conn_ind.pack(side="left", padx=SPACE_SM)

    def _build_notifications(self, count: int) -> None:
        """Bell con badge numérico opcional."""
        notif_frame = tk.Frame(self, bg=PRIMARY, width=48)
        notif_frame.pack(side="right", fill="y", padx=SPACE_SM)
        notif_frame.pack_propagate(False)

        inner = tk.Frame(notif_frame, bg=PRIMARY)
        inner.pack(expand=True)

        self._bell = tk.Label(
            inner,
            text="🔔",
            bg=PRIMARY,
            fg=TEXT_ON_DARK,
            font=("DejaVu Sans", 16),
            cursor="hand2",
        )
        self._bell.pack()
        self._bell.bind(
            "<Button-1>",
            lambda _e: self._on_notif_click() if self._on_notif_click else None,
        )
        self._bell.bind("<Enter>", lambda _e: self._bell.configure(fg=ACCENT_GOLD))
        self._bell.bind("<Leave>", lambda _e: self._bell.configure(fg=TEXT_ON_DARK))

        # Badge numérico (label superpuesto)
        self._notif_badge = tk.Label(
            inner,
            text="",
            bg=ACCENT_GOLD,
            fg=PRIMARY,
            font=("DejaVu Sans", 8, "bold"),
            padx=4,
            pady=0,
        )
        self.set_notifications_count(count)

    def _build_avatar(self, user_name: str, user_role: str) -> None:
        """Avatar circular con iniciales + label rol debajo."""
        avatar_outer = tk.Frame(self, bg=PRIMARY, width=100)
        avatar_outer.pack(side="right", fill="y", padx=(SPACE_SM, SPACE_LG))
        avatar_outer.pack_propagate(False)

        inner = tk.Frame(avatar_outer, bg=PRIMARY, cursor="hand2")
        inner.pack(expand=True)

        # Círculo del avatar via Canvas (32x32)
        avatar_color = role_color(user_role)
        initials = self._compute_initials(user_name)

        canvas = tk.Canvas(
            inner,
            width=32,
            height=32,
            bg=PRIMARY,
            highlightthickness=0,
            cursor="hand2",
        )
        canvas.pack(side="left")
        canvas.create_oval(0, 0, 31, 31, fill=avatar_color, outline=avatar_color)
        canvas.create_text(
            16,
            16,
            text=initials,
            fill=TEXT_ON_DARK,
            font=("DejaVu Sans", 10, "bold"),
        )

        # Texto rol debajo del avatar (arriba?). Spec dice "label debajo" —
        # como el header es bajo, ponemos rol a la derecha del avatar para
        # no romper la altura de 60px.
        text_frame = tk.Frame(inner, bg=PRIMARY)
        text_frame.pack(side="left", padx=(SPACE_SM, 0))

        role_label = tk.Label(
            text_frame,
            text=user_role.upper(),
            bg=PRIMARY,
            fg=TEXT_ON_DARK_MUTED,
            font=FONT_TINY,
        )
        role_label.pack(anchor="w")

        chevron = tk.Label(
            text_frame,
            text="▾",
            bg=PRIMARY,
            fg=TEXT_ON_DARK,
            font=FONT_SMALL,
        )
        chevron.pack(anchor="w")

        # Click handlers
        for w in (canvas, role_label, chevron, inner):
            w.bind(
                "<Button-1>",
                lambda _e: self._on_avatar_click() if self._on_avatar_click else None,
            )

    @staticmethod
    def _compute_initials(name: str) -> str:
        """Calcula iniciales (máx 2 letras) a partir de un nombre completo."""
        parts = [p for p in name.strip().split() if p]
        if not parts:
            return "??"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    # ─── API pública para actualizar estados ─────────────────────────────

    def set_sensor_status(self, state: State, tooltip: str | None = None) -> None:
        self._sensor_ind.set_state(state, tooltip)

    def set_sync_status(self, state: State, tooltip: str | None = None) -> None:
        self._sync_ind.set_state(state, tooltip)

    def set_ntp_status(self, state: State, tooltip: str | None = None) -> None:
        self._ntp_ind.set_state(state, tooltip)

    def set_connectivity_status(
        self, state: State, tooltip: str | None = None
    ) -> None:
        self._conn_ind.set_state(state, tooltip)
        # Cambiar icono según online/offline
        if state == "error":
            self._conn_ind.set_label("Offline")
        else:
            self._conn_ind.set_label("Online")

    def set_notifications_count(self, count: int) -> None:
        """Muestra/oculta el badge según count."""
        if count > 0:
            text = str(count) if count < 10 else "9+"
            self._notif_badge.configure(text=text)
            # Ubicación: superpuesto al bell, esquina superior derecha.
            # En Tkinter sin overlap absoluto, mejor a la derecha del bell.
            self._notif_badge.pack(side="left", padx=(2, 0))
        else:
            self._notif_badge.pack_forget()
