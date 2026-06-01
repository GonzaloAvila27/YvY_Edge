"""Modal de Catchup Recovery: configurar → ejecutar → resultado.

Tres estados visuales que se intercambian destruyendo y recreando el body:
    1. CONFIG: date picker + texto explicativo + botones cancelar/ejecutar.
    2. RUNNING: progressbar indeterminada + label de progreso.
    3. RESULT: muestra CatchupResult o error, con botón cerrar.

El alto del modal NO se fija. Crece según el contenido de cada estado.

Wrapping de callbacks para Tkinter: las callbacks que pasamos al
controller se wrappean con ``self.after(0, ...)`` antes de delegar al
controller. Esto garantiza que las actualizaciones de widgets ocurran
en el main thread, no en el thread del catchup.
"""

from __future__ import annotations

import calendar
import contextlib
import logging
import tkinter as tk
from datetime import UTC, datetime, timedelta, tzinfo
from enum import Enum
from tkinter import ttk

from yvy.application.use_cases.sensor.run_catchup_recovery import CatchupResult
from yvy.domain.sensor.exceptions import CatchupAlreadyRunningError
from yvy.presentation.components.modal import Modal
from yvy.presentation.controllers.sync_controller import SyncController
from yvy.presentation.theme import (
    BG_CARD,
    DANGER,
    FONT_BODY,
    FONT_H2,
    FONT_KPI_VALUE,
    FONT_MONO,
    FONT_SMALL,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SUCCESS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)


class _State(Enum):
    CONFIG = "config"
    RUNNING = "running"
    RESULT_OK = "result_ok"
    RESULT_ERROR = "result_error"


class CatchupModal(Modal):
    """Modal para disparar el RunCatchupRecoveryUseCase.

    Args:
        parent: ventana padre (típicamente MainApplication).
        controller: SyncController inyectado por la view padre.
        local_tz: zona horaria local. Se usa para construir el datetime
            tz-aware desde los Spinbox (que el use case requiere
            obligatoriamente).
        default_days_back: fecha default del picker = ahora - N días
            (default 7).
    """

    def __init__(
        self,
        parent: tk.Misc,
        controller: SyncController,
        local_tz: tzinfo,
        default_days_back: int = 7,
        auto_since: datetime | None = None,
    ) -> None:
        self._controller = controller
        self._local_tz = local_tz
        self._default_days_back = default_days_back
        self._auto_since = auto_since  # si se pasa, saltea CONFIG y dispara solo

        # Si hay auto_since, arrancamos directo en RUNNING
        self._state: _State = _State.RUNNING if auto_since is not None else _State.CONFIG
        self._body_frame: tk.Frame | None = None
        self._footer_frame: tk.Frame | None = None

        # Widgets del estado RUNNING (referencias para actualizar progreso)
        self._progress_bar: ttk.Progressbar | None = None
        self._progress_label: ttk.Label | None = None

        # Date picker widgets (estado CONFIG)
        self._day_var: tk.StringVar | None = None
        self._month_var: tk.StringVar | None = None
        self._year_var: tk.StringVar | None = None

        # Resultado o error guardado para renderizado
        self._last_result: CatchupResult | None = None
        self._last_error: Exception | None = None

        super().__init__(
            parent,
            title="Recuperar buffer histórico",
            width=520,
            on_close=None,
        )

        # Disparo automático cuando viene de startup (sin date picker)
        if self._auto_since is not None:
            self.after(100, self._run_auto_catchup)

    # ─── Hooks de Modal ──────────────────────────────────────────────────

    def body(self, parent: tk.Frame) -> None:
        """Body inicial: estado CONFIG."""
        self._body_frame = parent
        self._render_state()

    def buttons(self, parent: tk.Frame) -> None:
        """Footer dinámico según estado."""
        self._footer_frame = parent
        self._render_footer()

    # ─── Render por estado ───────────────────────────────────────────────

    def _render_state(self) -> None:
        """Limpia el body y lo repuebla según el estado actual."""
        if self._body_frame is None:
            return

        for child in self._body_frame.winfo_children():
            child.destroy()

        if self._state == _State.CONFIG:
            self._render_config(self._body_frame)
        elif self._state == _State.RUNNING:
            self._render_running(self._body_frame)
        elif self._state == _State.RESULT_OK:
            self._render_result_ok(self._body_frame)
        elif self._state == _State.RESULT_ERROR:
            self._render_result_error(self._body_frame)

        self._render_footer()

    def _render_footer(self) -> None:
        """Repuebla el footer según estado."""
        if self._footer_frame is None:
            return

        for child in self._footer_frame.winfo_children():
            child.destroy()

        if self._state == _State.CONFIG:
            ttk.Button(
                self._footer_frame,
                text="Cancelar",
                command=self.close,
                style="Secondary.TButton",
            ).pack(side="right", padx=(SPACE_SM, 0))
            ttk.Button(
                self._footer_frame,
                text="Ejecutar recuperación",
                command=self._on_execute_clicked,
                style="Primary.TButton",
            ).pack(side="right")
        elif self._state == _State.RUNNING:
            # Sin botones: el catchup no se cancela (lock atómico).
            ttk.Label(
                self._footer_frame,
                text="No cierres esta ventana. La recuperación está en curso.",
                style="Secondary.TLabel",
            ).pack(side="left")
        elif self._state in (_State.RESULT_OK, _State.RESULT_ERROR):
            ttk.Button(
                self._footer_frame,
                text="Cerrar",
                command=self.close,
                style="Primary.TButton",
            ).pack(side="right")

    # ─── Estado CONFIG ───────────────────────────────────────────────────

    def _render_config(self, parent: tk.Frame) -> None:
        """Date picker + texto explicativo."""
        # Texto explicativo
        ttk.Label(
            parent,
            text="Recuperar datos del buffer histórico del sensor",
            style="CardH3.TLabel",
        ).pack(anchor="w")

        explainer = tk.Label(
            parent,
            text=(
                "Ingresá la fecha desde la cual recuperar lecturas del "
                "buffer interno del sensor. Esta operación puede tardar "
                "varios minutos. Durante el proceso no se podrán cargar "
                "nuevas observaciones."
            ),
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
            wraplength=440,
            justify="left",
        )
        explainer.pack(anchor="w", pady=(SPACE_SM, SPACE_LG))

        # Date picker: 3 Spinbox (día, mes, año) + label arriba
        ttk.Label(
            parent,
            text="Recuperar desde:",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_SM))

        date_frame = tk.Frame(parent, bg=BG_CARD)
        date_frame.pack(anchor="w", pady=(0, SPACE_LG))

        # Default: hoy local - default_days_back
        default_dt = datetime.now(tz=self._local_tz) - timedelta(
            days=self._default_days_back
        )
        self._day_var = tk.StringVar(value=f"{default_dt.day:02d}")
        self._month_var = tk.StringVar(value=f"{default_dt.month:02d}")
        self._year_var = tk.StringVar(value=str(default_dt.year))

        ttk.Label(date_frame, text="Día:", style="Card.TLabel").grid(
            row=0, column=0, padx=(0, SPACE_SM), sticky="w"
        )
        ttk.Spinbox(
            date_frame,
            from_=1,
            to=31,
            width=4,
            textvariable=self._day_var,
            font=FONT_BODY,
            wrap=False,
        ).grid(row=0, column=1, padx=(0, SPACE_LG))

        ttk.Label(date_frame, text="Mes:", style="Card.TLabel").grid(
            row=0, column=2, padx=(0, SPACE_SM), sticky="w"
        )
        ttk.Spinbox(
            date_frame,
            from_=1,
            to=12,
            width=4,
            textvariable=self._month_var,
            font=FONT_BODY,
            wrap=False,
        ).grid(row=0, column=3, padx=(0, SPACE_LG))

        ttk.Label(date_frame, text="Año:", style="Card.TLabel").grid(
            row=0, column=4, padx=(0, SPACE_SM), sticky="w"
        )
        ttk.Spinbox(
            date_frame,
            from_=2020,
            to=2100,
            width=6,
            textvariable=self._year_var,
            font=FONT_BODY,
            wrap=False,
        ).grid(row=0, column=5)

        # Hint con la fecha resultante actualizada en vivo
        self._date_hint = tk.Label(
            parent,
            text="",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_SMALL,
        )
        self._date_hint.pack(anchor="w")

        # Trace para actualizar hint al cambiar
        for var in (self._day_var, self._month_var, self._year_var):
            var.trace_add("write", lambda *_a: self._update_date_hint())
        self._update_date_hint()

    def _update_date_hint(self) -> None:
        """Refresca el hint con la fecha parseada (o un mensaje de error)."""
        if not hasattr(self, "_date_hint"):
            return
        try:
            dt = self._parse_picker_date()
            self._date_hint.configure(
                text=f"Fecha: {_format_date_es(dt)} (hora local)",
                fg=TEXT_SECONDARY,
            )
        except ValueError as exc:
            self._date_hint.configure(text=f"⚠ {exc}", fg=DANGER)

    def _parse_picker_date(self) -> datetime:
        """Parsea los Spinbox a datetime tz-aware.

        Raises:
            ValueError si la fecha no es válida (ej. 31 de febrero) o
            si está en el futuro.
        """
        assert self._day_var and self._month_var and self._year_var
        try:
            day = int(self._day_var.get())
            month = int(self._month_var.get())
            year = int(self._year_var.get())
        except (ValueError, TypeError):
            raise ValueError("Fecha inválida") from None

        # Validar rango día/mes/año real
        if not (1 <= month <= 12):
            raise ValueError(f"Mes inválido: {month}")
        max_day = calendar.monthrange(year, month)[1]
        if not (1 <= day <= max_day):
            raise ValueError(f"Día inválido para {month}/{year}: {day}")

        dt = datetime(year, month, day, 0, 0, 0, tzinfo=self._local_tz)
        now_local = datetime.now(tz=self._local_tz)
        if dt > now_local:
            raise ValueError("La fecha no puede ser futura")

        return dt

    # ─── Estado RUNNING ──────────────────────────────────────────────────

    def _render_running(self, parent: tk.Frame) -> None:
        ttk.Label(
            parent,
            text="Recuperación en curso",
            style="CardH3.TLabel",
        ).pack(anchor="w", pady=(0, SPACE_LG))

        self._progress_bar = ttk.Progressbar(
            parent,
            mode="indeterminate",
            style="Primary.Horizontal.TProgressbar",
            length=440,
        )
        self._progress_bar.pack(anchor="w", pady=(0, SPACE_MD))
        self._progress_bar.start(15)  # ms entre frames

        self._progress_label = ttk.Label(
            parent,
            text="Iniciando lectura del buffer...",
            style="CardSecondary.TLabel",
        )
        self._progress_label.pack(anchor="w")

    def _update_progress(self, message: str) -> None:
        """Actualiza el label de progreso. Llamado desde el main thread."""
        if self._progress_label is not None:
            with contextlib.suppress(tk.TclError):
                # Modal cerrado mientras llegaba el callback
                self._progress_label.configure(text=message)

    # ─── Estado RESULT_OK ────────────────────────────────────────────────

    def _render_result_ok(self, parent: tk.Frame) -> None:
        assert self._last_result is not None
        r = self._last_result

        # Icono de éxito + título
        header = tk.Frame(parent, bg=BG_CARD)
        header.pack(anchor="w", pady=(0, SPACE_LG))

        tk.Label(
            header,
            text="✓",
            bg=BG_CARD,
            fg=SUCCESS,
            font=FONT_KPI_VALUE,
        ).pack(side="left", padx=(0, SPACE_MD))

        tk.Label(
            header,
            text="Recuperación completada",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H2,
        ).pack(side="left")

        # Tabla de resultados
        table = tk.Frame(parent, bg=BG_CARD)
        table.pack(anchor="w", fill="x")

        rows = [
            ("Slots leídos", str(r.slots_read), TEXT_PRIMARY),
            ("Nuevos", str(r.new_in_raw), SUCCESS),
            ("Ya estaban en DB", str(r.already_present), TEXT_SECONDARY),
            ("Errores de parsing", str(r.parse_errors),
             DANGER if r.parse_errors > 0 else TEXT_SECONDARY),
        ]
        for i, (label, value, color) in enumerate(rows):
            tk.Label(
                table,
                text=label + ":",
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                font=FONT_BODY,
                anchor="w",
                width=22,
            ).grid(row=i, column=0, sticky="w", pady=2)

            tk.Label(
                table,
                text=value,
                bg=BG_CARD,
                fg=color,
                font=FONT_MONO,
                anchor="w",
            ).grid(row=i, column=1, sticky="w", pady=2)

        # Resumen interpretativo
        if r.parse_errors > 0:
            warning = tk.Label(
                parent,
                text=(
                    f"Algunos slots no pudieron procesarse "
                    f"({r.parse_errors} de {r.slots_read}). El resto se "
                    f"guardó correctamente."
                ),
                bg=BG_CARD,
                fg=DANGER,
                font=FONT_SMALL,
                wraplength=440,
                justify="left",
            )
            warning.pack(anchor="w", pady=(SPACE_LG, 0))

    # ─── Estado RESULT_ERROR ─────────────────────────────────────────────

    def _render_result_error(self, parent: tk.Frame) -> None:
        assert self._last_error is not None
        exc = self._last_error

        # Header con icono de error
        header = tk.Frame(parent, bg=BG_CARD)
        header.pack(anchor="w", pady=(0, SPACE_LG))

        tk.Label(
            header,
            text="✕",
            bg=BG_CARD,
            fg=DANGER,
            font=FONT_KPI_VALUE,
        ).pack(side="left", padx=(0, SPACE_MD))

        tk.Label(
            header,
            text="Recuperación fallida",
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            font=FONT_H2,
        ).pack(side="left")

        # Mensaje específico según tipo de error
        if isinstance(exc, CatchupAlreadyRunningError):
            msg = (
                "Ya hay una recuperación en curso. Esperá a que termine "
                "antes de iniciar otra."
            )
        elif isinstance(exc, ValueError):
            msg = f"Parámetros inválidos: {exc}"
        else:
            msg = (
                f"Error inesperado durante la recuperación.\n\n"
                f"Tipo: {type(exc).__name__}\n"
                f"Mensaje: {exc}"
            )

        tk.Label(
            parent,
            text=msg,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=440,
            justify="left",
        ).pack(anchor="w")

    # ─── Handlers ────────────────────────────────────────────────────────

    def _run_auto_catchup(self) -> None:
        """Disparo automático desde startup — saltea el date picker."""
        assert self._auto_since is not None
        since_utc = (
            self._auto_since
            if self._auto_since.tzinfo is not None
            else self._auto_since.replace(tzinfo=UTC)
        )
        self._controller.trigger_catchup(
            since=since_utc,
            on_progress=lambda msg: self._safe_after(
                lambda: self._update_progress(msg)
            ),
            on_done=lambda result: self._safe_after(
                lambda: self._handle_done(result)
            ),
            on_error=lambda exc: self._safe_after(
                lambda: self._handle_error(exc)
            ),
        )

    def _on_execute_clicked(self) -> None:
        """Click en 'Ejecutar': valida fecha, transiciona a RUNNING, dispara."""
        try:
            since = self._parse_picker_date()
        except ValueError as exc:
            # Mostrar el error en el hint, no transicionar
            self._update_date_hint()
            logger.info("Validación de fecha falló: %s", exc)
            return

        # Convertir a UTC para el use case
        since_utc = since.astimezone(UTC)

        # Transicionar a RUNNING antes de disparar
        self._state = _State.RUNNING
        self._render_state()

        # Disparar el catchup. Wrappear callbacks con after(0, ...)
        # para volver al main thread.
        self._controller.trigger_catchup(
            since=since_utc,
            on_progress=lambda msg: self._safe_after(
                lambda: self._update_progress(msg)
            ),
            on_done=lambda result: self._safe_after(
                lambda: self._handle_done(result)
            ),
            on_error=lambda exc: self._safe_after(
                lambda: self._handle_error(exc)
            ),
        )

    def _safe_after(self, fn) -> None:  # type: ignore[no-untyped-def]
        """Schedule fn en el main loop. Silencia errores si el modal se cerró."""
        with contextlib.suppress(tk.TclError, RuntimeError):
            self.after(0, fn)

    def _handle_done(self, result: CatchupResult) -> None:
        if self._progress_bar is not None:
            with contextlib.suppress(tk.TclError):
                self._progress_bar.stop()
        self._last_result = result
        self._state = _State.RESULT_OK
        self._render_state()

    def _handle_error(self, exc: Exception) -> None:
        if self._progress_bar is not None:
            with contextlib.suppress(tk.TclError):
                self._progress_bar.stop()
        self._last_error = exc
        self._state = _State.RESULT_ERROR
        self._render_state()


# ─── Helpers ─────────────────────────────────────────────────────────────


_DAYS_ES = (
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
)
_MONTHS_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _format_date_es(dt: datetime) -> str:
    """Formato de fecha en español sin depender del locale del SO."""
    day_name = _DAYS_ES[dt.weekday()]
    month_name = _MONTHS_ES[dt.month - 1]
    return f"{day_name} {dt.day} de {month_name} de {dt.year}"
