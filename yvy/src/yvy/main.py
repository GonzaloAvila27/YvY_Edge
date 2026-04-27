"""Entry point de la aplicación YVY.

Comando: poetry run yvy
"""

import sys


def main() -> int:
    """Punto de entrada de la aplicación.

    Por ahora solo imprime versión y sale. En Fase 4 (UI base) se conecta
    con MainApplication de presentation.
    """
    from yvy import __version__

    print(f"YVY v{__version__}")
    print("Aplicación todavía no implementada.")
    print("Estado actual: Fase 0 cerrada (bootstrap del repo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
