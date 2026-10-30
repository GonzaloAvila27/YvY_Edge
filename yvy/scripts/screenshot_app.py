"""Captura screenshots de las pantallas principales para review visual."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from yvy.presentation.app import MainApplication, MockUser


def take_screenshot(filename: str) -> None:
    """Captura la pantalla X11 actual via imagemagick `import`."""
    subprocess.run(
        ["import", "-window", "root", filename],
        check=True,
    )


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    os.makedirs(out_dir, exist_ok=True)

    app = MainApplication()

    # 1. Login
    app.update()
    time.sleep(0.5)
    app.update()
    take_screenshot(f"{out_dir}/01_login.png")

    # 2. Navegar a main como admin
    user = MockUser(
        username="jperez",
        full_name="Juan Pérez",
        role="admin",
        iea_name="IEA Nº10 — Posadas",
        iea_cue="540178700",
    )
    app.show_main(user)
    app.update()
    time.sleep(0.5)
    app.update()
    take_screenshot(f"{out_dir}/02_dashboard_admin.png")

    # 3. Navegar a un placeholder
    app._navigate("usuarios")
    app.update()
    time.sleep(0.3)
    app.update()
    take_screenshot(f"{out_dir}/03_placeholder_usuarios.png")

    # 4. Sidebar colapsado
    app._navigate("dashboard")
    app.update()
    if app._sidebar:
        app._sidebar.toggle()
    app.update()
    time.sleep(0.3)
    app.update()
    take_screenshot(f"{out_dir}/04_sidebar_collapsed.png")

    app.destroy()
    print(f"✓ Screenshots guardados en {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
