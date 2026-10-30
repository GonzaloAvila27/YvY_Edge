"""Renderers: convierten reports de handlers en salida humana.

Separados de los handlers para que en Ola 2 (framework remoto) los
mismos handlers se reusen devolviendo JSON al cliente Core sin
imprimir nada localmente.
"""

from __future__ import annotations

from typing import Any

from yvy.cli.formatting import (
    Status,
    arrow_note,
    bold,
    header,
    row,
)

_STATUS_MAP = {
    "ok": Status.OK,
    "fail": Status.FAIL,
    "warn": Status.WARN,
    "info": Status.INFO,
    "neutral": Status.NEUTRAL,
}


def print_report(
    report: dict[str, Any],
    *,
    title: str,
    subtitle: str | None = None,
) -> None:
    """Imprime un report con formato estándar."""
    print(header(title, subtitle))
    print()

    # Calcular ancho de label dinámicamente para alinear
    labels = [c["name"] for c in report.get("checks", [])]
    label_width = max((len(name) for name in labels), default=20)
    label_width = min(label_width + 2, 30)  # cap para no romper en pantallas chicas

    for check in report.get("checks", []):
        status = _STATUS_MAP.get(check.get("status", "info"), Status.INFO)
        print(
            row(
                check["name"],
                status,
                check.get("detail"),
                label_width=label_width,
            )
        )

    notes = report.get("notes", [])
    if notes:
        print()
        for note in notes:
            print(arrow_note(note))

    summary = report.get("summary")
    if summary:
        print()
        if report.get("ok"):
            print(bold(summary))
        else:
            from yvy.cli.formatting import yellow

            print(bold(yellow(summary)))
