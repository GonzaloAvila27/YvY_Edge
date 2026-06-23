"""YVY Edge · Sistema meteorológico escolar offline-first.

Sistema de captura, persistencia y sincronización de datos meteorológicos
para Instituciones de Educación Agropecuaria de Misiones, Argentina.

Arquitectura: DDD + Hexagonal.
- domain/: reglas de negocio puras (sin imports externos).
- application/: casos de uso y ports (Protocol).
- infrastructure/: adaptadores (SQLite, pywws, HTTP, bcrypt).
- presentation/: UI Tkinter.
"""

# ─── Versión: FUENTE ÚNICA DE VERDAD ──────────────────────────────────────────
# La app corre desde el código fuente en producción (PYTHONPATH=src, no instalada
# como paquete), por lo que este __version__ es la referencia confiable en runtime
# (CLI, login, chequeo de versión del OTA en launch_app). pyproject.toml DEBE
# coincidir — lo enforcea tests/unit/test_version_consistency.py.
# Para bumpear la versión: cambiar acá Y en pyproject.toml [tool.poetry].version.
__version__ = "1.5.0"

# Versión de la capa de instalador/bootstrap (scripts INSTALL_UPDATE.bat, slots).
# Concepto distinto al de la app: solo cambia si cambia el instalador.
__installer_version__ = "1.4.0"
__author__ = "Gonzalo Rubens Avila"
__year__ = "2026"
