"""Controllers: mediadores entre views y use cases.

Decisión arquitectónica (Fase 4.5): se extiende el Protocol
``SyncRepository`` con métodos read-only en lugar de introducir CQRS.
Razonamiento completo en ``yvy_FASE4_RESUMEN.md``.

Controllers disponibles:
    - SyncController: dashboard de sync + trigger del catchup recovery.
    - AuthController: login, logout, cambio de propia password.

Próximos a agregar (fases siguientes):
    - DashboardController (Fase 5/7)
"""

from yvy.presentation.controllers.auth_controller import AuthController
from yvy.presentation.controllers.sync_controller import (
    SyncController,
    SyncDashboardData,
)
from yvy.presentation.controllers.users_admin_controller import UsersAdminController

__all__ = [
    "AuthController",
    "SyncController",
    "SyncDashboardData",
    "UsersAdminController",
]

