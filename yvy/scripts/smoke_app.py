"""Smoke test que instancia MainApplication, la cierra automáticamente.

Solo valida que la app arranca sin tracebacks. Si falla, hay un error
de instanciación o de configuración del theme.

Requiere display (Xvfb en CI). Local: corre directo.
"""

from __future__ import annotations

import sys

from yvy.presentation.app import MainApplication, MockUser


def main() -> int:
    app = MainApplication()

    # Cerrar después de 200ms en login
    app.after(200, lambda: _go_to_main(app))

    # Cerrar app a los 600ms tras llegar a main
    app.after(800, app.destroy)

    try:
        app.mainloop()
        print("OK App arranco, navego a main, cerro sin tracebacks.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


def _go_to_main(app: MainApplication) -> None:
    user = MockUser(
        username="jperez",
        full_name="Juan Pérez",
        role="admin",
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
    )
    app.show_main(user)
    # Probar navegación entre views
    app.after(100, lambda: app._navigate("usuarios"))
    app.after(200, lambda: app._navigate("logs"))
    app.after(300, lambda: app._navigate("dashboard"))
    # Probar toggle del sidebar
    app.after(400, lambda: app._sidebar.toggle() if app._sidebar else None)
    app.after(500, lambda: app._sidebar.toggle() if app._sidebar else None)


if __name__ == "__main__":
    sys.exit(main())
