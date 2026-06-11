"""Configura las credenciales de sync en un nodo YVY Edge instalado.

Escribe station_credentials.json en data/ y actualiza app_config (sync_server_url
y station_uuid) en la DB SQLite. No borra datos ni re-corre el onboarding completo.

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
import json
import shutil
import sys
from pathlib import Path
from uuid import UUID


def _find_root() -> Path:
    """Localiza C:\\YVY si existe; si no, sube desde __file__."""
    default = Path("C:/YVY")
    if default.exists() and (default / "src").exists():
        return default
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "src").exists():
        return candidate
    return Path.cwd()


def _validate_credentials(creds: dict) -> str | None:
    """Valida estructura. Devuelve mensaje de error o None si OK."""
    required = {"station_uuid", "key_version", "key_hmac_hex"}
    missing = required - creds.keys()
    if missing:
        return f"faltan campos: {', '.join(sorted(missing))}"
    try:
        UUID(str(creds["station_uuid"]))
    except ValueError:
        return f"station_uuid no es un UUID válido: {creds['station_uuid']!r}"
    try:
        int(creds["key_version"])
    except (ValueError, TypeError):
        return f"key_version no es entero: {creds['key_version']!r}"
    try:
        key_bytes = bytes.fromhex(str(creds["key_hmac_hex"]))
    except ValueError:
        return "key_hmac_hex no es hexadecimal válido"
    if len(key_bytes) < 32:
        return f"key_hmac_hex muy corto ({len(key_bytes)} bytes, mínimo 32)"
    return None


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

    # Aceptar URL también por variable de entorno (evita problemas con :// en shells)
    import os
    server_url = args.server_url or os.environ.get("YVY_SYNC_URL", "").strip()
    if not server_url:
        print("ERROR: falta la URL del servidor.")
        print("  Pasar con --server-url URL  o  set YVY_SYNC_URL=URL")
        return 1

    root = Path(args.root) if args.root else _find_root()
    if not root.exists():
        print(f"ERROR: no se encontró el directorio raíz: {root}")
        return 1

    # ── Validar archivo de credentials ──────────────────────────────────────
    creds_src = Path(args.credentials)
    if not creds_src.exists():
        print(f"ERROR: no se encontró el archivo: {creds_src}")
        return 1

    try:
        creds = json.loads(creds_src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: el archivo no es JSON válido: {exc}")
        return 1

    err = _validate_credentials(creds)
    if err:
        print(f"ERROR: credentials inválidas — {err}")
        return 1

    station_uuid = str(creds["station_uuid"])

    # ── Copiar credentials a data/ ───────────────────────────────────────────
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)
    dest = data_dir / "station_credentials.json"

    if dest.exists():
        backup = dest.with_suffix(".json.bak")
        try:
            shutil.copy2(dest, backup)
            print(f"  Backup del archivo anterior: {backup.name}")
        except PermissionError:
            print("  AVISO: no se pudo hacer backup (archivo en uso) — se sobreescribe igual")

    shutil.copy2(creds_src, dest)
    print(f"  Credentials escritas en:     {dest}")

    # ── Actualizar app_config en la DB ───────────────────────────────────────
    src_path = str(root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        from yvy.bootstrap import build_core_dependencies
    except ImportError as exc:
        print(f"ERROR: no se pudo importar el paquete yvy ({exc})")
        print(f"  Verificar que el proyecto está instalado en: {root}")
        return 1

    deps = build_core_dependencies(root=root, run_migrations_on_start=True)
    repo = deps.app_config_repo

    repo.set("sync_server_url", server_url)
    repo.set("station_uuid", station_uuid)

    print(f"  sync_server_url actualizado: {server_url}")
    print(f"  station_uuid actualizado:    {station_uuid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
