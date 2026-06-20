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
import math
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

from yvy.presentation.components.status_indicator import State, StatusIndicator
from yvy.presentation.theme import (
    ACCENT_GOLD,
    FONT_BODY_BOLD,
    FONT_LOGO,
    FONT_SMALL,
    FONT_TINY,
    HEADER_HEIGHT,
    PRIMARY,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_ON_DARK,
    TEXT_ON_DARK_MUTED,
    role_color,
)

logger = logging.getLogger(__name__)

_LOGO_PATH  = Path(__file__).resolve().parents[4] / "resources" / "logo.png"
_ICONS_DIR  = Path(__file__).resolve().parents[4] / "resources" / "ICONS"
# Tamaño del logo en el header (cabe en 60px de alto con padding 10px vertical)
_LOGO_W, _LOGO_H = 200, 50 

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
        on_theme_toggle: Callable[[], None] | None = None,
        notifications_count: int = 0,
    ) -> None:
        super().__init__(parent, bg=PRIMARY, height=HEADER_HEIGHT)
        self.pack_propagate(False)

        self._user_role = user_role.lower()
        self._on_notif_click = on_notifications_click
        self._on_avatar_click = on_avatar_click
        self._on_theme_toggle = on_theme_toggle

        # Refs para apply_theme
        self._theme_btn: tk.Button | None = None
        self._all_header_frames: list[tk.Frame] = []
        self._all_header_labels: list[tk.Label] = []

        self._build_logo()
        self._build_identity(iea_name, iea_cue)
        self._build_indicators()
        self._build_theme_toggle()
        self._build_notifications(notifications_count)
        self._build_avatar(user_name, user_role)

    # ─── Subsecciones ────────────────────────────────────────────────────

    def _build_logo(self) -> None:
        """Logo YVY Edge — PNG si existe resources/logo.png, texto fallback."""
        logo_frame = tk.Frame(self, bg=PRIMARY, width=_LOGO_W)
        logo_frame.pack(side="left", fill="y", padx=(SPACE_XL, 0))
        logo_frame.pack_propagate(False)

        inner = tk.Frame(logo_frame, bg=PRIMARY)
        inner.pack(expand=True, fill="y")

        photo = _load_logo(_LOGO_PATH, _LOGO_W, _LOGO_H)
        if photo is not None:
            lbl = tk.Label(inner, image=photo, bg=PRIMARY, cursor="arrow")
            lbl.image = photo  # evitar garbage collection
            lbl.pack(expand=True)
        else:
            # Fallback texto (mientras no haya PNG)
            tk.Label(
                inner, text="YVY", bg=PRIMARY, fg=SUCCESS, font=FONT_LOGO, anchor="w",
            ).pack(anchor="w")
            tk.Label(
                inner, text="Edge", bg=PRIMARY, fg="#7A9E1F",
                font=("DejaVu Sans", 10, "bold"), anchor="w",
            ).pack(anchor="w")

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

        # Cargar PNGs de campana (white normal, gold hover, red alerta)
        self._bell_img_normal: tk.PhotoImage | None = None
        self._bell_img_hover: tk.PhotoImage | None = None
        self._bell_img_alert: tk.PhotoImage | None = None
        try:
            self._bell_img_normal = tk.PhotoImage(file=str(_ICONS_DIR / "campana_white.png"))
            self._bell_img_hover  = tk.PhotoImage(file=str(_ICONS_DIR / "campana_gold.png"))
        except tk.TclError:
            pass
        try:
            self._bell_img_alert = tk.PhotoImage(file=str(_ICONS_DIR / "campana_red.png"))
        except tk.TclError:
            pass

        # Estado de alerta de update
        self._update_alert_active: bool = False
        self._blink_state: bool = False
        self._blink_after_id: str | None = None

        if self._bell_img_normal is not None:
            self._bell = tk.Label(inner, image=self._bell_img_normal, bg=PRIMARY, cursor="hand2")
            self._bell.bind("<Enter>", lambda _e: self._bell.configure(image=self._bell_img_hover))
            self._bell.bind("<Leave>", lambda _e: self._bell.configure(image=self._bell_img_normal))
        else:
            self._bell = tk.Label(
                inner, text="🔔", bg=PRIMARY, fg=TEXT_ON_DARK,
                font=("DejaVu Sans", 16), cursor="hand2",
            )
            self._bell.bind("<Enter>", lambda _e: self._bell.configure(fg=ACCENT_GOLD))
            self._bell.bind("<Leave>", lambda _e: self._bell.configure(fg=TEXT_ON_DARK))

        self._bell.pack()
        self._bell.bind(
            "<Button-1>",
            lambda _e: self._on_notif_click() if self._on_notif_click else None,
        )

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
        """Solo avatar circular con iniciales (sin texto de nombre/rol)."""
        avatar_outer = tk.Frame(self, bg=PRIMARY, width=52)
        avatar_outer.pack(side="right", fill="y", padx=(SPACE_SM, SPACE_LG))
        avatar_outer.pack_propagate(False)

        inner = tk.Frame(avatar_outer, bg=PRIMARY, cursor="hand2")
        inner.pack(expand=True)

        avatar_color = role_color(user_role)
        initials = self._compute_initials(user_name)

        canvas = tk.Canvas(
            inner, width=34, height=34,
            bg=PRIMARY, highlightthickness=0, cursor="hand2",
        )
        canvas.pack()
        # Hexágono flat-top centrado en 17,17 con radio 16
        cx, cy, r = 17, 17, 16
        pts = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        canvas.create_polygon(pts, fill=avatar_color, outline="")
        canvas.create_text(
            17, 17, text=initials, fill=TEXT_ON_DARK,
            font=("DejaVu Sans", 11, "bold"),
        )

        for w in (canvas, inner, avatar_outer):
            w.bind(
                "<Button-1>",
                lambda _e: self._on_avatar_click() if self._on_avatar_click else None,
            )

    def _build_theme_toggle(self) -> None:
        """Botón flat para cambiar entre light/dark mode."""
        from yvy.presentation.theme_manager import theme_manager
        frame = tk.Frame(self, bg=PRIMARY, width=90)
        frame.pack(side="right", fill="y", padx=(0, SPACE_SM))
        frame.pack_propagate(False)

        inner = tk.Frame(frame, bg=PRIMARY)
        inner.pack(expand=True)

        lbl = "Light Mode" if theme_manager.mode == "dark" else "Dark Mode"
        self._theme_btn = tk.Button(
            inner,
            text=lbl,
            relief="flat",
            bd=0,
            bg=PRIMARY,
            fg=TEXT_ON_DARK_MUTED,
            activebackground=PRIMARY,
            activeforeground=TEXT_ON_DARK,
            font=FONT_SMALL,
            cursor="hand2",
            command=self._handle_theme_toggle,
        )
        self._theme_btn.pack()

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
            self._notif_badge.pack(side="left", padx=(2, 0))
        else:
            self._notif_badge.pack_forget()

    def set_update_alert(self, active: bool) -> None:
        """Activa/desactiva el parpadeo rojo de la campana.

        Visible para TODOS los roles. El parpadeo es persistente mientras
        haya un update pendiente de instalar. Se cancela al instalar.
        """
        if active == self._update_alert_active:
            return
        self._update_alert_active = active
        if active:
            self._blink_state = False
            self._blink_tick()
        else:
            self._stop_blink()

    def _blink_tick(self) -> None:
        if not self._update_alert_active:
            return
        if not hasattr(self, "_bell") or not self._bell.winfo_exists():
            return
        self._blink_state = not self._blink_state
        if self._blink_state and self._bell_img_alert is not None:
            self._bell.configure(image=self._bell_img_alert)
        elif self._bell_img_normal is not None:
            self._bell.configure(image=self._bell_img_normal)
        self._blink_after_id = self.after(900, self._blink_tick)

    def _stop_blink(self) -> None:
        if self._blink_after_id is not None:
            try:
                self.after_cancel(self._blink_after_id)
            except Exception:
                pass
            self._blink_after_id = None
        if hasattr(self, "_bell") and self._bell.winfo_exists():
            if self._bell_img_normal is not None:
                self._bell.configure(image=self._bell_img_normal)

    def set_theme_toggle_enabled(self, enabled: bool) -> None:
        """Habilita o deshabilita el botón de dark/light mode."""
        if self._theme_btn is not None:
            self._theme_btn.configure(state="normal" if enabled else "disabled")

    def _handle_theme_toggle(self) -> None:
        """Callback del botón toggle — delega al handler externo."""
        if self._on_theme_toggle:
            self._on_theme_toggle()

    def apply_theme(self, palette: dict) -> None:
        """Reconfigura todos los widgets del header con la paleta dada."""
        h = palette["header"]
        # Recorrer TODO el árbol del header
        from yvy.presentation.theme_manager import recolor
        recolor(self, palette)
        # El canvas del header siempre tiene bg=header (el recolor lo maneja)
        # Actualizar texto del toggle button
        if self._theme_btn is not None:
            from yvy.presentation.theme_manager import theme_manager
            lbl = "Light Mode" if theme_manager.mode == "dark" else "Dark Mode"
            self._theme_btn.configure(
                text=lbl,
                bg=h, fg=palette["text_on_dark_muted"],
                activebackground=h, activeforeground=palette["text_on_dark"],
            )


# ─── Helper de carga de logo ──────────────────────────────────────────────────


def _load_logo(path: Path, width: int, height: int) -> "tk.PhotoImage | None":
    """Carga un PNG y lo escala a (width, height). Retorna None si falla.

    Usa Pillow si está disponible (escalado de calidad); fallback a
    tk.PhotoImage nativo (solo funciona si el PNG ya tiene el tamaño exacto).
    """
    if not path.exists():
        return None
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA")
        img.thumbnail((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        pass
    try:
        import tkinter as _tk
        return _tk.PhotoImage(file=str(path))
    except Exception:
        logger.warning("logo.load.failed", extra={"path": str(path)})
        return None
