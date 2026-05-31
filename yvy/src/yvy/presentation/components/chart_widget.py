"""ChartWidget — widget Tkinter reutilizable que envuelve matplotlib.

Soporta tres estados de overlay (loading / empty / error) y un estado
renderizado (canvas matplotlib visible). El método render() ejecuta la
función de dibujo en un thread para no congelar la UI de Tkinter.

El backend TkAgg debe estar configurado antes de importar este módulo
(lo hace launch_app.py al importar FigureCanvasTkAgg por primera vez).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from tkinter import ttk
import tkinter as tk

from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from yvy.presentation.theme import (
    BG_CARD,
    BORDER,
    DANGER,
    FONT_BODY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

_DPI: int = 96  # DPI base para convertir px → pulgadas


# ─── Helper público ────────────────────────────────────────────────────────────


def apply_yvy_style(ax: Axes) -> None:
    """Aplica estilo visual YVY a un Axes.

    Llamar después de ax.clear() o al inicializar el axes.
    Compatible con twin axes: llamar en cada eje creado.
    """
    ax.set_facecolor(BG_CARD)
    ax.grid(color=BORDER, linestyle="--", linewidth=0.8, alpha=0.5)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=10)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["left"].set_visible(True)
    ax.spines["bottom"].set_color(BORDER)
    ax.spines["left"].set_color(BORDER)

    ax.title.set_family("DejaVu Sans")
    ax.title.set_size(14)
    ax.title.set_weight("bold")
    ax.title.set_color(TEXT_PRIMARY)
    ax.xaxis.label.set_color(TEXT_SECONDARY)
    ax.xaxis.label.set_size(10)
    ax.yaxis.label.set_color(TEXT_SECONDARY)
    ax.yaxis.label.set_size(10)


# ─── Señal de datos vacíos ─────────────────────────────────────────────────────


class NoDataError(Exception):
    """Lanzar desde render_fn cuando no hay datos para el período."""


# ─── Widget ────────────────────────────────────────────────────────────────────


class ChartWidget(ttk.Frame):
    """Widget de gráfico matplotlib con estados de carga/vacío/error.

    Args:
        parent: widget padre Tkinter.
        width_px: ancho del área de gráfico en píxeles.
        height_px: alto del área de gráfico en píxeles.

    Uso típico::

        chart = ChartWidget(parent, width_px=720, height_px=320)
        chart.pack(fill="both", expand=True)

        def draw(fig, ax):
            if not data:
                raise NoDataError()
            ax.plot(x, y, color=PRIMARY)

        chart.render(draw)
    """

    def __init__(
        self,
        parent: tk.Misc,
        width_px: int = 720,
        height_px: int = 320,
    ) -> None:
        super().__init__(parent, style="Card.TFrame")

        self._width_px = width_px
        self._height_px = height_px
        self._rendering = False

        # ── Figura matplotlib ────────────────────────────────────────────
        fig_w = width_px / _DPI
        fig_h = height_px / _DPI
        self._fig = Figure(figsize=(fig_w, fig_h), dpi=_DPI, facecolor=BG_CARD)
        self._ax: Axes = self._fig.add_subplot(111)
        self._fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.14)
        apply_yvy_style(self._ax)

        # ── Canvas embebido ──────────────────────────────────────────────
        self._mpl_canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas_widget: tk.Widget = self._mpl_canvas.get_tk_widget()
        self._canvas_widget.configure(
            width=width_px,
            height=height_px,
            bg=BG_CARD,
            highlightthickness=0,
        )
        self._canvas_widget.grid(row=0, column=0, sticky="nsew")

        # ── Overlay de estado (loading / empty / error) ──────────────────
        self._state_frame = tk.Frame(
            self, bg=BG_CARD, width=width_px, height=height_px
        )
        self._state_frame.grid_propagate(False)
        self._state_label = tk.Label(
            self._state_frame,
            text="",
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            font=FONT_BODY,
            wraplength=width_px - 48,
            justify="center",
        )
        self._state_label.place(relx=0.5, rely=0.5, anchor="center")
        self._state_frame.grid(row=0, column=0, sticky="nsew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.show_loading()

    # ─── API pública ──────────────────────────────────────────────────────

    def show_loading(self) -> None:
        """Muestra el overlay de carga."""
        self._set_state("Cargando...", TEXT_SECONDARY)

    def show_empty(
        self,
        message: str = "Sin datos para el período seleccionado",
    ) -> None:
        """Muestra el overlay de estado vacío."""
        self._set_state(message, TEXT_SECONDARY)

    def show_error(self, message: str) -> None:
        """Muestra el overlay de error con el mensaje."""
        self._set_state(f"Error al cargar el gráfico\n{message}", DANGER)

    def render(self, render_fn: Callable[[Figure, Axes], None]) -> None:
        """Ejecuta render_fn en un thread y actualiza el canvas al terminar.

        Args:
            render_fn: función que recibe (Figure, Axes) y configura el
                gráfico. Puede lanzar ``NoDataError`` para ir a show_empty().

        El widget llama apply_yvy_style(ax) antes de invocar render_fn,
        por lo que no es necesario hacerlo dentro de ella (aunque no hace
        daño llamarlo nuevamente para twin axes).
        """
        if self._rendering:
            return
        self._rendering = True
        self.show_loading()

        chart_type = getattr(
            render_fn, "__qualname__", getattr(render_fn, "__name__", repr(render_fn))
        )

        def _worker() -> None:
            try:
                # Reconstruir axes para limpiar twin axes de renders previos
                self._fig.clear()
                self._fig.set_facecolor(BG_CARD)
                self._ax = self._fig.add_subplot(111)
                self._fig.subplots_adjust(left=0.08, right=0.96, top=0.88, bottom=0.14)
                apply_yvy_style(self._ax)

                render_fn(self._fig, self._ax)

            except NoDataError as exc:
                msg = str(exc) or "Sin datos para el período seleccionado"
                self.after(0, lambda m=msg: self.show_empty(m))
                return
            except Exception as exc:
                logger.error(
                    "chart.render.failed",
                    extra={"chart_type": chart_type, "error": str(exc)},
                    exc_info=True,
                )
                self.after(0, lambda m=str(exc): self.show_error(m))
                return
            finally:
                self._rendering = False

            self.after(0, self._flush_canvas)

        threading.Thread(target=_worker, daemon=True, name=f"chart-render-{chart_type}").start()

    # ─── Privados ─────────────────────────────────────────────────────────

    def _set_state(self, text: str, color: str) -> None:
        """Muestra el overlay de estado con texto y color dados."""
        self._state_label.configure(text=text, fg=color)
        self._state_frame.lift()

    def _flush_canvas(self) -> None:
        """Redibuja el canvas matplotlib. Siempre en el main thread."""
        try:
            self._mpl_canvas.draw()
            self._canvas_widget.lift()
        except Exception as exc:
            logger.warning("chart.flush.failed", extra={"error": str(exc)})
            self._set_state(f"Error al renderizar: {exc}", DANGER)
