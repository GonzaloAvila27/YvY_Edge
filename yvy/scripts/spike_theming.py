"""Spike de theming (INI-1 · 1.3). NO es parte de la app: se corre a mano.

Pregunta que responde
---------------------
Hay 19 llamadas a ``tk.Label``/``tk.Text`` sin ``bg``/``fg`` explícitos. Los
que no declaran ``bg`` nacen con el gris del sistema (``SystemButtonFace``) y
``recolor()`` no los reconoce, así que en tema oscuro quedan gris claro.

¿Se puede arreglar sin tocar los 19 call sites?

    A  baseline        cómo está hoy
    B  option database ``root.option_add("*Label.background", ...)``
    C  fallback de bg  en ``recolor``, tratar un color de sistema como la clave
                       "bg"/"surface" — espejo exacto de lo que el ``fg`` ya hace

El punto no es "¿pinta bien la primera vez?" sino **el toggle repetido**, y los
widgets creados *después* de un toggle (un modal abierto en oscuro).

Uso
---
    python scripts/spike_theming.py            # ventana con botón de toggle
    python scripts/spike_theming.py --auto     # sólo mide y dicta veredicto
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yvy.presentation.theme_manager import (
    _TAG_BG,
    _normalize_hex,
    recolor,
    theme_manager,
)

TOGGLES = 4


def _is_system_color(raw: str) -> bool:
    """``SystemButtonFace``, ``SystemWindow``… el gris que Tk pone por default."""
    return _normalize_hex(raw).startswith("system")


# ─── Estrategia C: el fallback propuesto para recolor() ───────────────────────


def apply_bg_fallback(widget: tk.Misc, palette: dict[str, str], in_card: bool = False) -> None:
    """Lo que haría el parche de 4 líneas en ``_apply_widget``.

    ``recolor`` ya hace esto para ``fg`` (negro o color-de-sistema → clave
    "text"); acá se hace lo mismo para ``bg``. Una vez que el widget queda con
    un hex de la paleta, los toggles siguientes lo reconocen solos por el
    mapa inverso, igual que a cualquier otro widget.
    """
    try:
        if _is_system_color(widget.cget("bg")):
            key = "surface" if in_card else "bg"
            widget.configure(bg=palette[key])
            # Sin el tag, el próximo toggle tiene que adivinar la clave desde el
            # hex — y DARK["surface"] == DARK["border"], así que adivina mal.
            setattr(widget, _TAG_BG, key)
    except Exception:
        pass

    is_card = False
    try:
        if widget.winfo_class() == "Frame":
            is_card = int(widget.cget("highlightthickness")) >= 1
    except Exception:
        pass
    for child in widget.winfo_children():
        apply_bg_fallback(child, palette, in_card or is_card)


# ─── Sujetos de prueba ────────────────────────────────────────────────────────


class Probe:
    """Un widget bajo observación, con el bg que *debería* tener."""

    def __init__(self, widget: tk.Misc, name: str, expect_key: str) -> None:
        self.widget = widget
        self.name = name
        self.expect_key = expect_key

    def bg(self) -> str:
        return _normalize_hex(self.widget.cget("bg"))

    def ok(self, palette: dict[str, str]) -> bool:
        return self.bg() == _normalize_hex(palette[self.expect_key])


def build_probes(parent: tk.Misc, palette: dict[str, str], *, tag: str) -> list[Probe]:
    """Reproduce los patrones reales de los 19 call sites marcados por el gate."""
    probes: list[Probe] = []

    # 1. tk.Label pelado sobre el fondo general — el caso de login_view:115
    plain = tk.Label(parent, text=f"[{tag}] Label sin bg ni fg")
    plain.pack(anchor="w", padx=8, pady=2)
    probes.append(Probe(plain, f"{tag}/Label pelado", "bg"))

    # 2. tk.Label dentro de una card (highlightthickness ≥ 1) — detail_modal
    card = tk.Frame(parent, bg=palette["surface"], highlightthickness=1)
    card.pack(fill="x", padx=8, pady=4)
    in_card = tk.Label(card, text=f"[{tag}] Label dentro de card")
    in_card.pack(anchor="w", padx=6, pady=6)
    probes.append(Probe(in_card, f"{tag}/Label en card", "surface"))

    # 3. tk.Text — onboarding/wizard_view:413. Nace con SystemWindow, no ...Face.
    txt = tk.Text(parent, height=2, width=40)
    txt.insert("1.0", f"[{tag}] Text sin bg ni fg")
    txt.pack(fill="x", padx=8, pady=2)
    probes.append(Probe(txt, f"{tag}/Text", "bg"))

    # 4. Control: un Label que SÍ declara bg. Debe seguir andando en todos lados.
    ok = tk.Label(parent, text=f"[{tag}] Label con bg explícito", bg=palette["bg"])
    ok.pack(anchor="w", padx=8, pady=2)
    probes.append(Probe(ok, f"{tag}/Label con bg", "bg"))

    return probes


# ─── Estrategias ──────────────────────────────────────────────────────────────


def strategy_baseline(root: tk.Tk, palette: dict[str, str]) -> None:
    recolor(root, palette)


def strategy_option_db(root: tk.Tk, palette: dict[str, str]) -> None:
    # option_add SÓLO afecta widgets creados después. Los ya vivos no releen.
    root.option_add("*Label.background", palette["bg"])
    root.option_add("*Text.background", palette["bg"])
    recolor(root, palette)


def strategy_bg_fallback(root: tk.Tk, palette: dict[str, str]) -> None:
    recolor(root, palette)
    apply_bg_fallback(root, palette)


STRATEGIES = {
    "A baseline": strategy_baseline,
    "B option-db": strategy_option_db,
    "C bg-fallback": strategy_bg_fallback,
}


# ─── Modo --auto ──────────────────────────────────────────────────────────────


def run_auto() -> int:
    print(f"Spike de theming — {TOGGLES} toggles por estrategia\n")
    verdicts: dict[str, tuple[int, int, bool]] = {}

    for name, strategy in STRATEGIES.items():
        theme_manager._mode = "light"
        root = tk.Tk()
        root.withdraw()

        # Widgets creados ANTES de cualquier toggle (el 99% de la app).
        probes = build_probes(root, theme_manager.palette, tag="pre")
        late: list[Probe] = []

        for i in range(TOGGLES):
            theme_manager._mode = "dark" if theme_manager.mode == "light" else "light"
            strategy(root, theme_manager.palette)
            # Tras el 1er toggle, creamos widgets nuevos: el modal abierto en oscuro.
            if i == 0:
                late = build_probes(root, theme_manager.palette, tag="post-toggle")
                strategy(root, theme_manager.palette)

        palette = theme_manager.palette
        all_probes = probes + late
        bad = [p for p in all_probes if not p.ok(palette)]
        control_ok = all(p.ok(palette) for p in all_probes if "con bg" in p.name)

        print(f"-- {name} | modo final={theme_manager.mode}")
        for p in all_probes:
            mark = "ok  " if p.ok(palette) else "MAL "
            print(f"   {mark} {p.name:34s} bg={p.bg()}  esperado={palette[p.expect_key]}")
        print()

        verdicts[name] = (len(all_probes) - len(bad), len(all_probes), control_ok)
        root.destroy()

    print("-- Veredicto")
    winner = None
    for name, (good, total, control_ok) in verdicts.items():
        status = "PASA" if good == total else f"falla {total - good}/{total}"
        regress = "" if control_ok else "  ROMPE el control con bg explicito!"
        print(f"   {name:16s} {good}/{total} widgets siguen al tema - {status}{regress}")
        if good == total and control_ok and winner is None:
            winner = name

    print()
    if winner is None:
        print("Ninguna estrategia sirve -> 1.3.2 rama B: hace falta la widget factory (4.2.3).")
        return 1
    print(f"Gana: {winner} -> 1.3.2 rama A: se arregla sin tocar los call sites.")
    return 0


# ─── Modo visual ──────────────────────────────────────────────────────────────


def run_gui() -> int:
    theme_manager._mode = "light"
    root = tk.Tk()
    root.title("Spike de theming — INI-1 · 1.3")
    root.geometry("560x620")

    strategy_name = tk.StringVar(value="C bg-fallback")
    verdict = tk.StringVar(value="")
    probes: list[Probe] = []

    bar = tk.Frame(root)
    bar.pack(fill="x", pady=6)
    tk.Label(bar, text="Estrategia:").pack(side="left", padx=6)
    for name in STRATEGIES:
        tk.Radiobutton(bar, text=name, variable=strategy_name, value=name).pack(side="left")

    body = tk.Frame(root, bg=theme_manager.palette["bg"])
    body.pack(fill="both", expand=True, padx=8, pady=8)
    probes.extend(build_probes(body, theme_manager.palette, tag="pre"))

    def do_toggle() -> None:
        theme_manager._mode = "dark" if theme_manager.mode == "light" else "light"
        palette = theme_manager.palette
        body.configure(bg=palette["bg"])
        STRATEGIES[strategy_name.get()](root, palette)
        bad = [p.name for p in probes if not p.ok(palette)]
        verdict.set(
            f"modo={theme_manager.mode}  ·  "
            + ("TODOS siguen al tema" if not bad else f"quedaron atrás: {', '.join(bad)}")
        )

    def add_late() -> None:
        """Simula abrir un modal con el tema ya cambiado."""
        palette = theme_manager.palette
        probes.extend(build_probes(body, palette, tag="post-toggle"))
        STRATEGIES[strategy_name.get()](root, palette)

    actions = tk.Frame(root)
    actions.pack(fill="x", pady=4)
    tk.Button(actions, text="Toggle claro/oscuro", command=do_toggle).pack(side="left", padx=6)
    tk.Button(actions, text="Crear widgets ahora (modal)", command=add_late).pack(side="left")

    tk.Label(root, textvariable=verdict, wraplength=540, justify="left").pack(
        fill="x", padx=8, pady=6
    )
    tk.Label(
        root,
        text=(
            "Qué mirar: togglear 4-5 veces. Los 'Label pelado', 'Label en card' y 'Text'\n"
            "deben cambiar de color. El 'Label con bg' es el control: nunca debe romperse.\n"
            "Después apretar 'Crear widgets ahora' con el tema oscuro puesto: los nuevos\n"
            "tienen que nacer bien, no en gris."
        ),
        justify="left",
        anchor="w",
    ).pack(fill="x", padx=8, pady=(0, 8))

    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--auto", action="store_true", help="Mide y dicta veredicto, sin ventana.")
    args = parser.parse_args()
    try:
        return run_auto() if args.auto else run_gui()
    except tk.TclError as exc:
        print(f"Sin display: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
