"""YVY Edge · Sistema meteorológico escolar offline-first.

Sistema de captura, persistencia y sincronización de datos meteorológicos
para Instituciones de Educación Agropecuaria de Misiones, Argentina.

Arquitectura: DDD + Hexagonal.
- domain/: reglas de negocio puras (sin imports externos).
- application/: casos de uso y ports (Protocol).
- infrastructure/: adaptadores (SQLite, pywws, HTTP, bcrypt).
- presentation/: UI Tkinter.
"""

__version__ = "1.3.0"
__installer_version__ = "1.3.0"
__author__ = "Gonzalo Rubens Avila"
__year__ = "2026"
