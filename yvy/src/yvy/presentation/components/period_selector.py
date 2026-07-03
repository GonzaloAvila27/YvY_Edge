"""PeriodSelector — widget Tkinter de selección de período temporal.

Exports públicos:
    PeriodSelector  — widget con 5 presets + modo personalizado.
    resolve_preset  — helper puro: (preset, now, tz) → (start, end).
    PeriodRange     — re-exportado desde domain.observatorio para
                      que los callers solo importen desde este módulo.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from datetime import date, datetime, timedelta
from tkinter import ttk
from zoneinfo import ZoneInfo

from yvy.domain.observatorio.period_range import PeriodRange
from yvy.domain.observatorio.range_clamp import clamp_to_data_range
from yvy.presentation.theme import (
    BG_CARD,
    BORDER,
    DANGER,
    FONT_BODY,
    FONT_SMALL,
    PRIMARY,
    SPACE_SM,
    SPACE_XS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

__all__ = ["PeriodRange", "PeriodSelector", "resolve_preset"]

logger = logging.getLogger(__name__)

# ─── Presets disponibles ──────────────────────────────────────────────────────

_ALL_PRESETS: list[str] = ["24h", "7d", "30d", "1y", "custom"]

_PRESET_LABELS: dict[str, str] = {
    "24h":    "24h",
    "7d":     "7d",
    "30d":    "30d",
    "1y":     "1y",
    "custom": "Personalizado",
}

_PRESET_DELTA: dict[str, timedelta] = {
    "24h": timedelta(days=1),
    "7d":  timedelta(days=7),
    "30d": timedelta(days=30),
    "1y":  timedelta(days=365),
}


# ─── Helper puro ─────────────────────────────────────────────────────────────


def resolve_preset(
    preset: str,
    now: datetime,
    tz: ZoneInfo,  # reservado para presets de calendario futuros (ej. "mes actual")
) -> tuple[datetime, datetime]:
    """Resuelve un preset a (start, end) relativos a *now*.

    Args:
        preset: uno de "24h", "7d", "30d", "1y".
        now:    datetime timezone-aware que actúa como extremo superior.
        tz:     zona horaria de la estación (reservada para futuros presets).

    Returns:
        Tupla (start, end) donde end == now y start == now - delta.

    Raises:
        ValueError: si preset == "custom" (requiere fechas del usuario)
            o si el preset es desconocido.
    """
    if preset == "custom":
        raise ValueError(
            "'custom' no tiene resolución automática; "
            "el usuario debe ingresar las fechas manualmente."
        )
    delta = _PRESET_DELTA.get(preset)
    if delta is None:
        valid = list(_PRESET_DELTA)
        raise ValueError(f"Preset desconocido: {preset!r}. Válidos: {valid}")
    return now - delta, now


# ─── Widget ───────────────────────────────────────────────────────────────────


class PeriodSelector(tk.Frame):
    """Widget de selección de período temporal con 5 presets y modo personalizado.

    Layout de 2 filas (grid):
      fila 0 — "Período:" + 5 radiobuttons (siempre visible).
      fila 1 — custom_row (date pickers) O clamp_label, mutuamente excluyentes.

    Args:
        parent:          widget padre Tkinter.
        on_change:       callback invocado con el nuevo PeriodRange cuando cambia.
        tz:              zona horaria de la estación (ZoneInfo).
        initial_preset:  preset seleccionado al crear el widget (default "7d").
    """

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_change: Callable[[PeriodRange], None],
        tz: ZoneInfo,
        initial_preset: str = "7d",
        allowed_presets: list[str] | None = None,
    ) -> None:
        super().__init__(parent, bg=BG_CARD)
        self._on_change = on_change
        self._tz = tz
        self._allowed_presets: list[str] = (
            allowed_presets if allowed_presets is not None else list(_ALL_PRESETS)
        )
        # Asegurar que el preset inicial esté en la lista permitida
        first_allowed = self._allowed_presets[0] if self._allowed_presets else "7d"
        effective_preset = (
            initial_preset if initial_preset in self._allowed_presets else first_allowed
        )
        self._preset_var = tk.StringVar(value=effective_preset)
        self._custom_range: PeriodRange | None = None

        self._build()

    # ─── Construcción ─────────────────────────────────────────────────────

    def _make_date_entry(self) -> tk.Entry:
        """Entry de fecha con colores explícitos.

        Sin bg/fg explícitos, en dark mode recolor pinta el texto claro pero la
        caja queda blanca (no reconoce "white"/SystemWindow) → texto invisible.
        """
        return tk.Entry(
            self._custom_row, width=11, font=FONT_SMALL,
            bg=BG_CARD, fg=TEXT_PRIMARY, relief="flat", bd=0,
            highlightbackground=BORDER, highlightthickness=1, highlightcolor=PRIMARY,
            insertbackground=TEXT_PRIMARY,
        )

    def _build(self) -> None:
        # ── Fila 0: label + radiobuttons ──────────────────────────────────
        top_row = tk.Frame(self, bg=BG_CARD)
        top_row.grid(row=0, column=0, sticky="w")

        tk.Label(
            top_row, text="Período:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_BODY
        ).pack(side="left", padx=(0, SPACE_SM))

        single_preset = len(self._allowed_presets) == 1

        for preset in _ALL_PRESETS:
            if preset not in self._allowed_presets:
                continue
            if single_preset:
                # Preset único → etiqueta fija (sin radiobutton, menos intrusivo)
                tk.Label(
                    top_row,
                    text=_PRESET_LABELS[preset],
                    bg=BG_CARD,
                    fg=TEXT_SECONDARY,
                    font=FONT_BODY,
                ).pack(side="left", padx=(0, SPACE_SM))
            else:
                ttk.Radiobutton(
                    top_row,
                    text=_PRESET_LABELS[preset],
                    variable=self._preset_var,
                    value=preset,
                    command=self._on_preset_changed,
                ).pack(side="left", padx=(0, SPACE_SM))

        # ── Fila 1a: date picker (oculto por defecto) ──────────────────
        self._custom_row = tk.Frame(self, bg=BG_CARD)

        tk.Label(
            self._custom_row, text="Desde:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL
        ).pack(side="left")
        self._from_entry = self._make_date_entry()
        self._from_entry.pack(side="left", padx=(SPACE_XS, SPACE_SM))

        tk.Label(
            self._custom_row, text="Hasta:", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL
        ).pack(side="left")
        self._until_entry = self._make_date_entry()
        self._until_entry.pack(side="left", padx=(SPACE_XS, SPACE_SM))

        ttk.Button(
            self._custom_row,
            text="Aplicar",
            command=self._on_apply_clicked,
            style="Secondary.TButton",
        ).pack(side="left", padx=(0, SPACE_SM))

        self._date_error_lbl = tk.Label(
            self._custom_row, text="", bg=BG_CARD, fg=DANGER, font=FONT_SMALL
        )
        self._date_error_lbl.pack(side="left")

        # ── Fila 1b: nota de clamp (oculto por defecto) ────────────────
        self._clamp_lbl = tk.Label(
            self, text="", bg=BG_CARD, fg=TEXT_SECONDARY, font=FONT_SMALL
        )

        # Si el preset inicial es "custom", mostrar el date picker
        if self._preset_var.get() == "custom":
            self._custom_row.grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))

    # ─── API pública ───────────────────────────────────────────────────────

    def get_period_range(self) -> PeriodRange:
        """Devuelve el PeriodRange actual según el estado del widget.

        Raises:
            ValueError: si el preset es "custom" y las fechas son inválidas
                o start >= end.
        """
        preset = self._preset_var.get()
        if preset == "custom":
            return self._parse_custom_range()
        start, end = resolve_preset(preset, datetime.now(self._tz), self._tz)
        return PeriodRange(start=start, end=end, preset_label=preset)

    def notify_clamped(
        self,
        actual_min: datetime | None,
        actual_max: datetime | None,
    ) -> None:
        """Muestra u oculta la nota de clamp según si los datos cubren el rango pedido.

        Debe llamarse desde el main thread (usar self.after(0, ...) si viene
        de un thread de render).

        Args:
            actual_min: timestamp más antiguo en los datos cargados.
            actual_max: timestamp más reciente en los datos cargados.
        """
        # En modo custom, el usuario controla el rango explícitamente;
        # no mostramos nota de clamp para no interferir con la UI.
        if self._preset_var.get() == "custom":
            self._clamp_lbl.grid_remove()
            return

        try:
            requested = self.get_period_range()
        except Exception:
            self._clamp_lbl.grid_remove()
            return

        _, was_clamped = clamp_to_data_range(requested, actual_min, actual_max)

        if was_clamped and actual_min is not None and actual_min > requested.start:
            local_min = actual_min.astimezone(self._tz)
            self._clamp_lbl.configure(
                text=f"Mostrando datos desde {local_min.strftime('%d %b %Y')}"
            )
            self._custom_row.grid_remove()
            self._clamp_lbl.grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))
        else:
            self._clamp_lbl.grid_remove()

    # ─── Handlers internos ─────────────────────────────────────────────────

    def _on_preset_changed(self) -> None:
        preset = self._preset_var.get()
        self._clamp_lbl.grid_remove()

        if preset == "custom":
            self._show_custom_row()
        else:
            self._custom_row.grid_remove()
            try:
                period = self.get_period_range()
                self._on_change(period)
            except Exception as exc:
                logger.debug("Callback de cambio de período falló (ignorado): %s", exc)

    def _on_apply_clicked(self) -> None:
        try:
            period = self._parse_custom_range()
        except ValueError as exc:
            self._date_error_lbl.configure(text=str(exc))
            return

        self._date_error_lbl.configure(text="")
        self._custom_range = period
        self._on_change(period)

    def _show_custom_row(self) -> None:
        self._date_error_lbl.configure(text="")
        # Pre-poblar con el rango del último preset si las entradas están vacías
        if not self._from_entry.get().strip():
            now = datetime.now(self._tz)
            week_ago = now - timedelta(days=7)
            self._from_entry.insert(0, week_ago.strftime("%Y-%m-%d"))
            self._until_entry.insert(0, now.strftime("%Y-%m-%d"))
        self._custom_row.grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))

    def _parse_custom_range(self) -> PeriodRange:
        """Parsea y valida las entradas de fecha en modo custom.

        Raises:
            ValueError: con mensaje en español si el formato o el rango es inválido.
        """
        from_str = self._from_entry.get().strip()
        until_str = self._until_entry.get().strip()

        try:
            from_date = date.fromisoformat(from_str)
        except ValueError:
            raise ValueError("Desde: formato AAAA-MM-DD")

        try:
            until_date = date.fromisoformat(until_str)
        except ValueError:
            raise ValueError("Hasta: formato AAAA-MM-DD")

        start = datetime(from_date.year, from_date.month, from_date.day, tzinfo=self._tz)
        end = datetime(
            until_date.year, until_date.month, until_date.day, 23, 59, 59, tzinfo=self._tz
        )

        if start >= end:
            raise ValueError("Desde debe ser anterior a Hasta")

        return PeriodRange(start=start, end=end, preset_label="custom")
