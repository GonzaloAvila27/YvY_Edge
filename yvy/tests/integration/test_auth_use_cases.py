"""Tests integration de los use cases de auth con DB + hasher reales.

A diferencia de los tests con mocks (que validan la lógica del use case),
estos tests validan que el use case + repos + hasher funcionan juntos.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from yvy.application.use_cases.auth.change_password import ChangePasswordUseCase
from yvy.application.use_cases.auth.create_user import (
    MAX_ADMINS,
    CreateUserUseCase,
)
from yvy.application.use_cases.auth.login import LoginUseCase
from yvy.application.use_cases.auth.manage_user import (
    SetUserActiveUseCase,
    ToggleExportFlagUseCase,
)
from yvy.domain.auth.enums import AuditEventType, Role
from yvy.domain.auth.exceptions import (
    CannotDeactivateLastAdminError,
    InvalidCredentialsError,
    SuperadminAlreadyExistsError,
    SuperadminProtectedError,
    TooManyAdminsError,
    UserInactiveError,
    UsernameAlreadyExistsError,
    WeakPasswordError,
)
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository
from yvy.infrastructure.system.clock import FrozenClock


# ─── Fixtures de use cases ───────────────────────────────────────────────


@pytest.fixture
def login_use_case(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
    fast_hasher: BcryptPasswordHasher,
) -> LoginUseCase:
    return LoginUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
        hasher=fast_hasher,
        time_provider=FrozenClock(
            datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        ),
    )


@pytest.fixture
def create_user_use_case(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
    fast_hasher: BcryptPasswordHasher,
) -> CreateUserUseCase:
    return CreateUserUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
        hasher=fast_hasher,
    )


@pytest.fixture
def change_password_use_case(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
    fast_hasher: BcryptPasswordHasher,
) -> ChangePasswordUseCase:
    return ChangePasswordUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
        hasher=fast_hasher,
    )


@pytest.fixture
def set_active_use_case(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
) -> SetUserActiveUseCase:
    return SetUserActiveUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
    )


@pytest.fixture
def toggle_export_use_case(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
) -> ToggleExportFlagUseCase:
    return ToggleExportFlagUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
    )


# ═════════════════════════════════════════════════════════════════════════
# CreateUserUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCreateUser:
    def test_creates_alumno(
        self, create_user_use_case: CreateUserUseCase
    ) -> None:
        user = create_user_use_case.execute(
            username="alice",
            full_name="Alice Smith",
            password="strongpass123",
            role=Role.ALUMNO,
        )
        assert user.id is not None
        assert user.role == Role.ALUMNO
        assert user.is_active is True
        assert user.can_export_raw is False

    def test_rejects_weak_password(
        self, create_user_use_case: CreateUserUseCase
    ) -> None:
        with pytest.raises(WeakPasswordError):
            create_user_use_case.execute(
                username="alice",
                full_name="Alice",
                password="short",
                role=Role.ALUMNO,
            )

    def test_rejects_duplicate_username(
        self, create_user_use_case: CreateUserUseCase
    ) -> None:
        create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="strongpass123",
            role=Role.ALUMNO,
        )
        with pytest.raises(UsernameAlreadyExistsError):
            create_user_use_case.execute(
                username="alice",
                full_name="Alice2",
                password="strongpass456",
                role=Role.PROFESOR,
            )

    def test_enforces_max_common_admins(
        self, create_user_use_case: CreateUserUseCase
    ) -> None:
        """Superadmin + 2 admins comunes OK; el 3er admin común falla."""
        create_user_use_case.execute(
            username="superuser",
            full_name="Super User",
            password="strongpass1",
            role=Role.SUPERADMIN,
        )
        create_user_use_case.execute(
            username="admin1",
            full_name="Admin One",
            password="strongpass2",
            role=Role.ADMIN,
        )
        # El superadmin NO cuenta contra el cap de comunes: el 2do admin común OK.
        create_user_use_case.execute(
            username="admin2",
            full_name="Admin Two",
            password="strongpass3",
            role=Role.ADMIN,
        )

        # El 3er admin común debe fallar
        with pytest.raises(TooManyAdminsError):
            create_user_use_case.execute(
                username="admin3",
                full_name="Admin Three",
                password="strongpass4",
                role=Role.ADMIN,
            )

    def test_superadmin_is_singleton(
        self, create_user_use_case: CreateUserUseCase
    ) -> None:
        """No se puede crear un segundo superadmin desde el use case."""
        create_user_use_case.execute(
            username="superuser",
            full_name="Super User",
            password="strongpass1",
            role=Role.SUPERADMIN,
        )
        with pytest.raises(SuperadminAlreadyExistsError):
            create_user_use_case.execute(
                username="superuser2",
                full_name="Super User 2",
                password="strongpass2",
                role=Role.SUPERADMIN,
            )

    def test_max_admins_constant_is_2(self) -> None:
        assert MAX_ADMINS == 2

    def test_audit_logged(
        self,
        create_user_use_case: CreateUserUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        create_user_use_case.execute(
            username="newbie",
            full_name="New Bie",
            password="strongpass",
            role=Role.ALUMNO,
        )

        recent = audit_log_repo.list_recent(limit=10)
        events = [e.event_type for e in recent]
        assert AuditEventType.USER_CREATED in events


# ═════════════════════════════════════════════════════════════════════════
# LoginUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestLogin:
    def test_successful_login_returns_user(
        self,
        login_use_case: LoginUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="goodpassword",
            role=Role.PROFESOR,
        )

        user = login_use_case.execute("alice", "goodpassword")
        assert user.username == "alice"
        assert user.role == Role.PROFESOR

    def test_unknown_user_raises_invalid_credentials(
        self, login_use_case: LoginUseCase
    ) -> None:
        with pytest.raises(InvalidCredentialsError):
            login_use_case.execute("ghost", "anything")

    def test_wrong_password_raises_invalid_credentials(
        self,
        login_use_case: LoginUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="correctpass",
            role=Role.ALUMNO,
        )
        with pytest.raises(InvalidCredentialsError):
            login_use_case.execute("alice", "wrongpass")

    def test_inactive_user_raises_user_inactive(
        self,
        login_use_case: LoginUseCase,
        create_user_use_case: CreateUserUseCase,
        set_active_use_case: SetUserActiveUseCase,
    ) -> None:
        # Necesitamos al menos 2 admins activos para poder desactivar uno;
        # pero alice es profesor, no admin: la deshabilitamos sin issue.
        u = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="goodpass",
            role=Role.PROFESOR,
        )
        set_active_use_case.execute(target_user_id=u.id, is_active=False)

        with pytest.raises(UserInactiveError):
            login_use_case.execute("alice", "goodpass")

    def test_login_updates_last_login(
        self,
        login_use_case: LoginUseCase,
        create_user_use_case: CreateUserUseCase,
        user_repo: SQLiteUserRepository,
    ) -> None:
        u = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="goodpass",
            role=Role.ALUMNO,
        )
        assert u.last_login is None

        login_use_case.execute("alice", "goodpass")

        refreshed = user_repo.find_by_id(u.id)
        assert refreshed is not None
        assert refreshed.last_login is not None

    def test_failed_login_audited(
        self,
        login_use_case: LoginUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        try:
            login_use_case.execute("ghost", "anything")
        except InvalidCredentialsError:
            pass

        recent = audit_log_repo.list_recent(limit=5)
        assert recent[0].event_type == AuditEventType.LOGIN_FAILED
        assert recent[0].username == "ghost"
        assert recent[0].metadata["reason"] == "user_not_found"

    def test_failed_login_does_not_log_password(
        self,
        login_use_case: LoginUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        """CRÍTICO: el password intentado NO debe aparecer en metadata."""
        create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="correctpass",
            role=Role.ALUMNO,
        )
        try:
            login_use_case.execute("alice", "secret_attempted_password")
        except InvalidCredentialsError:
            pass

        recent = audit_log_repo.list_recent(limit=5)
        # Buscamos el LOGIN_FAILED de alice
        failed = next(
            (e for e in recent if e.event_type == AuditEventType.LOGIN_FAILED
             and e.username == "alice"),
            None,
        )
        assert failed is not None
        meta_str = str(failed.metadata)
        assert "secret_attempted_password" not in meta_str


# ═════════════════════════════════════════════════════════════════════════
# ChangePasswordUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestChangePassword:
    def test_self_service_with_correct_old_password(
        self,
        change_password_use_case: ChangePasswordUseCase,
        login_use_case: LoginUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        u = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="oldpass123",
            role=Role.ALUMNO,
        )

        change_password_use_case.execute(
            target_user_id=u.id,
            new_password="newpass456",
            old_password="oldpass123",
            actor_user_id=u.id,
        )

        # Login con new password debe funcionar
        login_use_case.execute("alice", "newpass456")

        # Login con old password debe fallar
        with pytest.raises(InvalidCredentialsError):
            login_use_case.execute("alice", "oldpass123")

    def test_self_service_with_wrong_old_password(
        self,
        change_password_use_case: ChangePasswordUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        u = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="correctold",
            role=Role.ALUMNO,
        )
        with pytest.raises(InvalidCredentialsError):
            change_password_use_case.execute(
                target_user_id=u.id,
                new_password="newpass",
                old_password="wrongold",
                actor_user_id=u.id,
            )

    def test_admin_reset_no_old_password_required(
        self,
        change_password_use_case: ChangePasswordUseCase,
        create_user_use_case: CreateUserUseCase,
        login_use_case: LoginUseCase,
    ) -> None:
        admin = create_user_use_case.execute(
            username="admin1",
            full_name="Admin",
            password="adminpass",
            role=Role.ADMIN,
        )
        target = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="oldpass00",
            role=Role.ALUMNO,
        )

        # Admin resetea sin saber el old
        change_password_use_case.execute(
            target_user_id=target.id,
            new_password="newpass_by_admin",
            old_password=None,
            actor_user_id=admin.id,
        )

        login_use_case.execute("alice", "newpass_by_admin")

    def test_admin_cannot_reset_superadmin_password(
        self,
        change_password_use_case: ChangePasswordUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        """Un admin no puede resetear la password del superadmin desde la UI."""
        superadmin = create_user_use_case.execute(
            username="superuser",
            full_name="Super User",
            password="superpass0",
            role=Role.SUPERADMIN,
        )
        admin = create_user_use_case.execute(
            username="admin1",
            full_name="Admin",
            password="adminpass",
            role=Role.ADMIN,
        )

        with pytest.raises(SuperadminProtectedError):
            change_password_use_case.execute(
                target_user_id=superadmin.id,
                new_password="hacked_by_admin",
                old_password=None,
                actor_user_id=admin.id,
            )

    def test_superadmin_can_change_own_password(
        self,
        change_password_use_case: ChangePasswordUseCase,
        create_user_use_case: CreateUserUseCase,
        login_use_case: LoginUseCase,
    ) -> None:
        """Self-service: el superadmin sí puede cambiar su propia password."""
        superadmin = create_user_use_case.execute(
            username="superuser",
            full_name="Super User",
            password="superpass0",
            role=Role.SUPERADMIN,
        )

        change_password_use_case.execute(
            target_user_id=superadmin.id,
            new_password="new_superpass",
            old_password="superpass0",
            actor_user_id=superadmin.id,
        )

        login_use_case.execute("superuser", "new_superpass")


# ═════════════════════════════════════════════════════════════════════════
# SetUserActiveUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestSetUserActive:
    def test_cannot_deactivate_superadmin(
        self,
        set_active_use_case: SetUserActiveUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        """El superadmin es inmutable desde la UI: no se desactiva."""
        u = create_user_use_case.execute(
            username="superuser",
            full_name="Super User",
            password="adminpass",
            role=Role.SUPERADMIN,
        )

        with pytest.raises(SuperadminProtectedError):
            set_active_use_case.execute(
                target_user_id=u.id, is_active=False
            )

    def test_cannot_deactivate_last_common_admin(
        self,
        set_active_use_case: SetUserActiveUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        """Defensivo: sin superadmin, no podés desactivar el único admin común."""
        u = create_user_use_case.execute(
            username="onlyadmin",
            full_name="Only Admin",
            password="adminpass",
            role=Role.ADMIN,
        )

        with pytest.raises(CannotDeactivateLastAdminError):
            set_active_use_case.execute(
                target_user_id=u.id, is_active=False
            )

    def test_can_deactivate_admin_when_another_active_exists(
        self,
        set_active_use_case: SetUserActiveUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        super_u = create_user_use_case.execute(
            username="superuser",
            full_name="Super",
            password="strongpass",
            role=Role.SUPERADMIN,
        )
        admin = create_user_use_case.execute(
            username="admin1",
            full_name="Admin",
            password="strongpass",
            role=Role.ADMIN,
        )

        # Desactivar el admin (no superadmin) está OK porque queda super activo
        set_active_use_case.execute(target_user_id=admin.id, is_active=False)

    def test_can_deactivate_non_admin_freely(
        self,
        set_active_use_case: SetUserActiveUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        u = create_user_use_case.execute(
            username="alice",
            full_name="Alice",
            password="strongpass",
            role=Role.ALUMNO,
        )
        set_active_use_case.execute(target_user_id=u.id, is_active=False)


# ═════════════════════════════════════════════════════════════════════════
# ToggleExportFlagUseCase
# ═════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
class TestToggleExport:
    def test_toggles_flag_on_profesor(
        self,
        toggle_export_use_case: ToggleExportFlagUseCase,
        create_user_use_case: CreateUserUseCase,
        user_repo: SQLiteUserRepository,
    ) -> None:
        u = create_user_use_case.execute(
            username="profe1",
            full_name="Profesor",
            password="strongpass",
            role=Role.PROFESOR,
        )
        assert u.can_export_raw is False

        toggle_export_use_case.execute(target_user_id=u.id, can_export=True)

        refreshed = user_repo.find_by_id(u.id)
        assert refreshed is not None
        assert refreshed.can_export_raw is True

    def test_rejects_enabling_flag_on_alumno(
        self,
        toggle_export_use_case: ToggleExportFlagUseCase,
        create_user_use_case: CreateUserUseCase,
    ) -> None:
        """Política: alumnos NUNCA pueden tener can_export_raw=True."""
        u = create_user_use_case.execute(
            username="alumno1",
            full_name="Alumno",
            password="strongpass",
            role=Role.ALUMNO,
        )
        with pytest.raises(ValueError, match="Alumnos no pueden"):
            toggle_export_use_case.execute(
                target_user_id=u.id, can_export=True
            )
