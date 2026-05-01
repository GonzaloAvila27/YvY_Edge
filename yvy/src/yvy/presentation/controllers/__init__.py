"""Controllers: mediadores entre views y use cases.

Decisión arquitectónica (Fase 4.5): se extiende el Protocol
``SyncRepository`` con métodos read-only en lugar de introducir CQRS.
Razonamiento completo en ``yvy_FASE4_RESUMEN.md``.

Controllers disponibles:
    - SyncController: dashboard de sync + trigger del catchup recovery.

Próximos a agregar (fases siguientes):
    - AuthController (Fase 6)
    - DashboardController (Fase 5/7)
"""

from yvy.presentation.controllers.sync_controller import (
    SyncController,
    SyncDashboardData,
)

__all__ = [
    "SyncController",
    "SyncDashboardData",
]

