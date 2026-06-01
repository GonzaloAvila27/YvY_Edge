"""Pantalla de Login.

Layout:
    - Fondo crema
    - Card centrado 380x440 con: logo + título + subtítulo + línea
      decorativa + inputs usuario/contraseña + botón INGRESAR
    - Footer fino con indicadores de estado + versión

El use case real de auth viene en Fase 6. Por ahora, esta view recibe
un callback `on_login(username, password)` y lo dispara al click.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk

from yvy.presentation.components.status_indicator import StatusIndicator
from yvy.presentation.theme import (
    BG_CARD,
    BG_CREAM,
    BORDER,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_DISPLAY,
    FONT_SMALL,
    FONT_TINY,
    PRIMARY,
    SPACE_2XL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_LOGO_LOGIN_PATH = Path(__file__).resolve().parents[4] / "resources" / "logo_login.png"
# Ancho y alto del logo en el login card (sobre fondo blanco del card)
_LOGO_LOGIN_W, _LOGO_LOGIN_H = 220, 70


class LoginView(tk.Frame):
    """Frame de login.

    Args:
        parent: widget padre.
        on_login: callback `(username, password) -> None` ejecutado al
            hacer click en INGRESAR. La validación real es responsabilidad
            del controller (Fase 6).
        version: string de versión a mostrar en el footer (ej. "1.2.0").
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_login: Callable[[str, str], None],
        version: str | None = None,
        installer_version: str | None = None,
    ) -> None:
        super().__init__(parent, bg=BG_CREAM)

        from yvy import __installer_version__, __version__
        self._version = version or __version__
        self._installer_version = installer_version or __installer_version__
        self._on_login = on_login
        self._password_visible = False

        self._build_card()
        self._build_footer()

    # ─── Card central ────────────────────────────────────────────────────

    def _build_card(self) -> None:
        """Card centrado con form de login."""
        center = tk.Frame(self, bg=BG_CREAM)
        center.pack(expand=True, fill="both")

        wrapper = tk.Frame(center, bg=BG_CREAM)
        wrapper.place(relx=0.5, rely=0.5, anchor="center")

        card = tk.Frame(
            wrapper,
            bg=BG_CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack()

        # Créditos debajo del card — pequeño, no invasivo
        tk.Label(
            wrapper,
            text=(
                f"Desarrollado por Gonzalo Rubens Avila · 2026\n"
                f"v{self._version}  ·  instalador v{self._installer_version}"
            ),
            bg=BG_CREAM,
            fg=TEXT_SECONDARY,
            font=FONT_TINY,
            justify="center",
        ).pack(pady=(SPACE_SM, 0))

        # Logo — PNG si existe, fallback a texto
        logo_frame = tk.Frame(card, bg=BG_CARD)
        logo_frame.pack(pady=(SPACE_2XL, SPACE_MD))

        photo = _load_logo(_LOGO_LOGIN_PATH, _LOGO_LOGIN_W, _LOGO_LOGIN_H)
        if photo is not None:
            lbl = tk.Label(logo_frame, image=photo, bg=BG_CARD)
            lbl.image = photo  # evitar garbage collection
            lbl.pack()
            # Con PNG no mostramos título de texto redundante
            tk.Label(
                card,
                text="Sistema Meteorológico Escolar",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(pady=(0, SPACE_MD))
        else:
            # Fallback: canvas con texto (sin rectángulo azul)
            logo_canvas = tk.Canvas(
                logo_frame, width=80, height=80, bg=BG_CARD, highlightthickness=0,
            )
            logo_canvas.pack()
            logo_canvas.create_text(
                40, 36, text="YVY", fill=PRIMARY, font=("DejaVu Sans", 22, "bold"),
            )
            logo_canvas.create_text(
                40, 58, text="Edge", fill=SUCCESS, font=("DejaVu Sans", 11, "bold"),
            )
            tk.Label(
                card, text="YVY Edge", bg=BG_CARD, fg=PRIMARY, font=FONT_DISPLAY,
            ).pack()
            tk.Label(
                card,
                text="Sistema Meteorológico Escolar",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_SMALL,
            ).pack(pady=(0, SPACE_MD))

        # Línea decorativa oliva
        line = tk.Frame(card, bg=SUCCESS, height=2, width=200)
        line.pack(pady=(0, SPACE_LG))

        # Campos
        form = tk.Frame(card, bg=BG_CARD)
        form.pack(fill="x", padx=SPACE_2XL, pady=(0, SPACE_2XL))

        # Usuario
        tk.Label(
            form,
            text="Usuario",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
            anchor="w",
        ).pack(fill="x", pady=(0, SPACE_SM))

        self._user_entry = ttk.Entry(form, font=FONT_BODY)
        self._user_entry.pack(fill="x", ipady=4)

        # Contraseña
        tk.Label(
            form,
            text="Contraseña",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_BODY_BOLD,
            anchor="w",
        ).pack(fill="x", pady=(SPACE_MD, SPACE_SM))

        pwd_wrapper = tk.Frame(form, bg=BG_CARD)
        pwd_wrapper.pack(fill="x")

        self._pwd_entry = ttk.Entry(pwd_wrapper, font=FONT_BODY, show="●")
        self._pwd_entry.pack(side="left", fill="x", expand=True, ipady=4)

        self._eye_btn = tk.Label(
            pwd_wrapper,
            text="👁",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=("DejaVu Sans", 12),
            cursor="hand2",
            padx=SPACE_SM,
        )
        self._eye_btn.pack(side="right")
        self._eye_btn.bind("<Button-1>", self._toggle_password)

        # Botón
        login_btn = ttk.Button(
            form,
            text="INGRESAR",
            command=self._handle_login,
            style="Primary.TButton",
        )
        login_btn.pack(fill="x", pady=(SPACE_XL, 0), ipady=4)

        # Enter en cualquier campo dispara login
        self._user_entry.bind("<Return>", lambda _e: self._handle_login())
        self._pwd_entry.bind("<Return>", lambda _e: self._handle_login())

        # Foco inicial
        self._user_entry.focus_set()

    # ─── Footer ──────────────────────────────────────────────────────────

    def _build_footer(self) -> None:
        """Barra inferior con indicadores de sistema y versión."""
        footer = tk.Frame(self, bg=PRIMARY, height=32)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        inner = tk.Frame(footer, bg=PRIMARY)
        inner.pack(expand=True, fill="both", padx=SPACE_LG)

        # Indicadores izquierda
        StatusIndicator(
            inner,
            icon_key="online",
            label="Online",
            state="ok",
            bg=PRIMARY,
            on_dark=True,
        ).pack(side="left", padx=(0, SPACE_LG), pady=SPACE_SM)

        StatusIndicator(
            inner,
            icon_key="radio",
            label="Sensor: live",
            state="ok",
            bg=PRIMARY,
            on_dark=True,
        ).pack(side="left", padx=SPACE_LG, pady=SPACE_SM)

        StatusIndicator(
            inner,
            icon_key="clock",
            label="NTP OK",
            state="ok",
            bg=PRIMARY,
            on_dark=True,
        ).pack(side="left", padx=SPACE_LG, pady=SPACE_SM)

        # Versión a la derecha
        tk.Label(
            inner,
            text=f"v{self._version}",
            bg=PRIMARY,
            fg="#B0B7C0",
            font=FONT_TINY,
        ).pack(side="right", pady=SPACE_SM)

    # ─── Handlers ────────────────────────────────────────────────────────

    def _toggle_password(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        self._password_visible = not self._password_visible
        self._pwd_entry.configure(show="" if self._password_visible else "●")
        self._eye_btn.configure(text="👁‍🗨" if self._password_visible else "👁")

    def _handle_login(self) -> None:
        username = self._user_entry.get().strip()
        password = self._pwd_entry.get()

        if not username or not password:
            logger.info("Login: campos vacíos, no se dispara callback.")
            return

        logger.info("Login submit: user=%s", username)
        try:
            self._on_login(username, password)
        except Exception:
            logger.exception("Error en callback on_login")

    def clear(self) -> None:
        """Limpia los inputs (útil tras logout)."""
        self._user_entry.delete(0, "end")
        self._pwd_entry.delete(0, "end")
        self._user_entry.focus_set()


# ─── Helper ───────────────────────────────────────────────────────────────────


def _load_logo(path: Path, width: int, height: int) -> "tk.PhotoImage | None":
    """Carga PNG y escala a (width, height). None si falla o no existe."""
    if not path.exists():
        return None
    try:
        from PIL import Image, ImageTk
        img = Image.open(path).convert("RGBA")
        img = img.resize((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        pass
    try:
        return tk.PhotoImage(file=str(path))
    except Exception:
        logger.warning("logo_login.load.failed", extra={"path": str(path)})
        return None
