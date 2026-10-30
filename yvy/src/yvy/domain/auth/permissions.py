"""Permisos centralizados.

Una sola fuente de verdad para "puede X user hacer Y acción". NO
distribuir lógica de permisos por handlers; importar este objeto y
preguntar.

Convención: cada método empieza con ``can_``, recibe un User (puede ser
None si querés permitir consultas anónimas, no aplicable acá), devuelve
bool. Si el user es None, todo devuelve False (defensivo).
"""

from __future__ import annotations

from yvy.domain.auth.enums import Role
from yvy.domain.auth.models import User


class Permissions:
    """Stateless. Sin __init__. Métodos estáticos."""

    # ─── Acciones que cualquier usuario logueado puede hacer ─────────────

    @staticmethod
    def can_login(user: User | None) -> bool:
        """True si el user puede loguear (existe y está activo)."""
        return user is not None and user.is_active

    @staticmethod
    def can_load_observation(user: User | None) -> bool:
        """Cargar observación: cualquier user activo."""
        return user is not None and user.is_active

    @staticmethod
    def can_view_dashboard(user: User | None) -> bool:
        """Dashboard: cualquier user activo. Versión simple para alumno."""
        return user is not None and user.is_active

    @staticmethod
    def dashboard_is_simple_view(user: User | None) -> bool:
        """True si al user solo le mostramos la vista simplificada."""
        return user is not None and user.role == Role.ALUMNO

    # ─── Sync ────────────────────────────────────────────────────────────

    @staticmethod
    def can_view_sync_status(user: User | None) -> bool:
        """Ver Sync status: profesor, admin, superadmin (no alumno)."""
        if user is None or not user.is_active:
            return False
        return user.role in (Role.PROFESOR, Role.ADMIN, Role.SUPERADMIN)

    @staticmethod
    def can_trigger_catchup(user: User | None) -> bool:
        """Disparar catchup recovery: admin o superadmin."""
        if user is None or not user.is_active:
            return False
        return user.is_admin

    # ─── User management ─────────────────────────────────────────────────

    @staticmethod
    def can_manage_users(user: User | None) -> bool:
        """Crear, editar, desactivar users: admin o superadmin."""
        if user is None or not user.is_active:
            return False
        return user.is_admin

    @staticmethod
    def can_create_admin(user: User | None) -> bool:
        """Crear users con rol admin: solo superadmin.

        Admin común crea profesores y alumnos pero no otros admins.
        """
        if user is None or not user.is_active:
            return False
        return user.role == Role.SUPERADMIN

    @staticmethod
    def can_toggle_export_flag(user: User | None) -> bool:
        """Activar/desactivar can_export_raw en otros users."""
        return Permissions.can_manage_users(user)

    # ─── Data access ─────────────────────────────────────────────────────

    @staticmethod
    def can_view_admin_data(user: User | None) -> bool:
        """Ver Admin/Datos: profesor, admin, superadmin."""
        if user is None or not user.is_active:
            return False
        return user.role in (Role.PROFESOR, Role.ADMIN, Role.SUPERADMIN)

    @staticmethod
    def can_export_data(user: User | None) -> bool:
        """Exportar sensor_data (procesado).

        Solo por rol: profesor, admin, superadmin. Para uso interno de
        la IEA (informes a directivos, comparativas, etc.). NO requiere
        flag adicional.
        """
        if user is None or not user.is_active:
            return False
        return user.role in (Role.PROFESOR, Role.ADMIN, Role.SUPERADMIN)

    @staticmethod
    def can_import_data(user: User | None) -> bool:
        """Importar CSV de sensor_data (datos históricos reales IEA).

        Mismo nivel que can_export_data: profesor, admin, superadmin.
        La importación es idempotente (INSERT OR IGNORE) pero es una
        operación de escritura, por lo que no se permite a alumnos.
        """
        if user is None or not user.is_active:
            return False
        return user.role in (Role.PROFESOR, Role.ADMIN, Role.SUPERADMIN)

    @staticmethod
    def can_export_raw(user: User | None) -> bool:
        """Exportar sensor_raw (crudo).

        Doble condición: rol válido (no alumno) Y flag explícito
        ``can_export_raw=True``. Para envío externo de datos sin procesar
        (típicamente a la tecnicatura para uso académico).
        """
        if user is None or not user.is_active:
            return False
        if user.role == Role.ALUMNO:
            return False
        return user.can_export_raw

    @staticmethod
    def can_view_logs(user: User | None) -> bool:
        """Ver Admin/Logs: admin o superadmin."""
        if user is None or not user.is_active:
            return False
        return user.is_admin

    # ─── Retention ───────────────────────────────────────────────────────

    @staticmethod
    def can_configure_retention(user: User | None) -> bool:
        """Editar policy de retención: admin o superadmin."""
        if user is None or not user.is_active:
            return False
        return user.is_admin

    @staticmethod
    def can_force_retention(user: User | None) -> bool:
        """Forzar corrida manual de retention: solo superadmin."""
        if user is None or not user.is_active:
            return False
        return user.role == Role.SUPERADMIN

    # ─── Empirical observations ──────────────────────────────────────────

    @staticmethod
    def can_create_empirical_observation(user: User | None) -> bool:
        """Cualquier usuario activo puede crear observaciones empíricas."""
        return not (user is None or not user.is_active)

    @staticmethod
    def can_create_empirical_event(user: User | None) -> bool:
        """Cualquier usuario activo puede registrar eventos puntuales."""
        return not (user is None or not user.is_active)

    @staticmethod
    def can_list_empirical_observations(user: User | None) -> bool:
        """Ver lista de observaciones: cualquier usuario activo."""
        return not (user is None or not user.is_active)

    @staticmethod
    def can_mark_observation_anomaly(user: User | None) -> bool:
        """Marcar anomalía: reservado a profesor, admin o superadmin."""
        if user is None or not user.is_active:
            return False
        return user.role in (Role.PROFESOR, Role.ADMIN, Role.SUPERADMIN)
