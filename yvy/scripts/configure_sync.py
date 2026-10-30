"""Configura las credenciales de sync en un nodo YVY Edge instalado.

Escribe station_credentials.json en data/ y actualiza app_config (sync_server_url
y station_uuid) en la DB SQLite. No borra datos ni re-corre el onboarding completo.

**Este script es un wrapper fino** (INI-2 · 2.2.1 · H7): toda la lógica vive en
``yvy.cli.handlers.configure_sync``. Antes duplicaba la validación de credentials,
la copia con backup y la escritura de app_config — y su copia leía el JSON con
``utf-8`` mientras el handler usa ``utf-8-sig``, así que un archivo con BOM
(típico de editores de Windows) fallaba por acá y no por el CLI.

Acá sólo se resuelve el root, se arman las dependencias y se imprime el resultado.

Uso desde la raíz del proyecto instalado:
    python scripts/configure_sync.py \\
        --credentials E:\\iea7_credentials.json \\
        --server-url https://yvy-edge.tecnicatura.edu.ar

    python scripts/configure_sync.py \\
        --credentials E:\\iea7_credentials.json \\
        --server-url https://yvy-edge.tecnicatura.edu.ar \\
        --root C:\\YVY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _find_root() -> Path:
    """Localiza C:\\YVY si existe; si no, sube desde __file__."""
    default = Path("C:/YVY")
    if default.exists() and (default / "src").exists():
        return default
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "src").exists():
        return candidate
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="configure_sync",
        description="Configura credenciales de sync en un nodo YVY Edge instalado.",
    )
    parser.add_argument(
        "--credentials",
        required=True,
        metavar="PATH",
        help="Ruta al archivo station_credentials.json.",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        metavar="URL",
        help="URL base del servidor YVY Core. Si no se pasa, se lee de YVY_SYNC_URL.",
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="PATH",
        help="Raíz del proyecto instalado (default: C:\\YVY).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _find_root()
    if not root.exists():
        print(f"ERROR: no se encontró el directorio raíz: {root}")
        return 1

    src_path = str(root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        from yvy.bootstrap import build_core_dependencies
        from yvy.cli.handlers import configure_sync
    except ImportError as exc:
        print(f"ERROR: no se pudo importar el paquete yvy ({exc})")
        print(f"  Verificar que el proyecto está instalado en: {root}")
        return 1

    deps = build_core_dependencies(root=root, run_migrations_on_start=True)

    # force=True preserva el contrato histórico de este script y del .bat:
    # CONFIGURAR_SYNC.bat es una acción explícita del técnico, así que siempre
    # reconfigura. (El `python -m yvy configure-sync` es idempotente a propósito
    # porque lo corren los instaladores.)
    report = configure_sync(
        deps,
        creds_path=Path(args.credentials),
        server_url=args.server_url,
        force=True,
    )

    for note in report["notes"]:
        print(f"  {note}")

    if not report["ok"]:
        print(f"ERROR: {report['error']}")
        if report["reason"] == "no_server_url":
            print("  Pasar con --server-url URL  o  set YVY_SYNC_URL=URL")
        return 1

    print(f"  Credentials escritas en:     {report['dest_path']}")
    print(f"  sync_server_url actualizado: {report['server_url']}")
    print(f"  station_uuid actualizado:    {report['station_uuid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
