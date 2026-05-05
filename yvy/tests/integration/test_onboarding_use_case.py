"""Tests integration de CompleteOnboardingUseCase con DB real."""

from __future__ import annotations

import pytest

from yvy.application.use_cases.auth.complete_onboarding import (
    AdminCreationData,
    CompleteOnboardingUseCase,
    KEY_CUE,
    KEY_HARDWARE_FINGERPRINT,
    KEY_ONBOARDING_COMPLETED_AT,
    KEY_SCHOOL_NAME,
    KEY_STATION_UUID,
    OnboardingData,
)
from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.domain.auth.enums import AuditEventType, Role
from yvy.domain.auth.exceptions import (
    UsernameAlreadyExistsError,
    WeakPasswordError,
)
from yvy.infrastructure.auth.bcrypt_hasher import BcryptPasswordHasher
from yvy.infrastructure.persistence.app_config_repository import AppConfigRepository
from yvy.infrastructure.persistence.connection import SQLiteConnectionFactory
from yvy.infrastructure.persistence.sqlite_audit_log_repository import (
    SQLiteAuditLogRepository,
)
from yvy.infrastructure.persistence.sqlite_user_repository import SQLiteUserRepository


@pytest.fixture
def app_config_repo(db_factory: SQLiteConnectionFactory) -> AppConfigRepository:
    return AppConfigRepository(db_factory)


@pytest.fixture
def onboarding_uc(
    user_repo: SQLiteUserRepository,
    audit_log_repo: SQLiteAuditLogRepository,
    fast_hasher: BcryptPasswordHasher,
    app_config_repo: AppConfigRepository,
) -> CompleteOnboardingUseCase:
    create_user_uc = CreateUserUseCase(
        user_repo=user_repo,
        audit_repo=audit_log_repo,
        hasher=fast_hasher,
    )
    return CompleteOnboardingUseCase(
        create_user_uc=create_user_uc,
        audit_repo=audit_log_repo,
        app_config_repo=app_config_repo,
    )


def _data(with_secondary: bool = False, **overrides) -> OnboardingData:
    primary = AdminCreationData(
        username="director",
        full_name="Juan Pérez",
        password="director2026",
    )
    secondary = (
        AdminCreationData(
            username="vicedir",
            full_name="María González",
            password="vicedir2026",
        )
        if with_secondary
        else None
    )
    base = dict(
        cue="540178700",
        school_name="IEA Nº10 — Posadas",
        school_short_name="IEA10",
        timezone="America/Argentina/Cordoba",
        primary_admin=primary,
        secondary_admin=secondary,
        hardware_fingerprint=None,
    )
    base.update(overrides)
    return OnboardingData(**base)


@pytest.mark.integration
class TestCompleteOnboarding:
    def test_creates_primary_superadmin(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        user_repo: SQLiteUserRepository,
    ) -> None:
        result = onboarding_uc.execute(_data())

        primary = user_repo.find_by_id(result.primary_admin_id)
        assert primary is not None
        assert primary.role == Role.SUPERADMIN
        assert primary.username == "director"
        assert result.secondary_admin_id is None

    def test_creates_both_admins(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        user_repo: SQLiteUserRepository,
    ) -> None:
        result = onboarding_uc.execute(_data(with_secondary=True))

        primary = user_repo.find_by_id(result.primary_admin_id)
        secondary = user_repo.find_by_id(result.secondary_admin_id)
        assert primary is not None and secondary is not None
        assert primary.role == Role.SUPERADMIN
        assert secondary.role == Role.ADMIN

    def test_persists_iea_config(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        app_config_repo: AppConfigRepository,
    ) -> None:
        result = onboarding_uc.execute(_data())

        assert app_config_repo.get(KEY_CUE) == "540178700"
        assert app_config_repo.get(KEY_SCHOOL_NAME) == "IEA Nº10 — Posadas"
        assert app_config_repo.get(KEY_STATION_UUID) == result.station_uuid

    def test_persists_hardware_fingerprint_when_present(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        app_config_repo: AppConfigRepository,
    ) -> None:
        fp = "abcdef12-3456-7890-abcd-ef1234567890"
        onboarding_uc.execute(_data(hardware_fingerprint=fp))

        assert app_config_repo.get(KEY_HARDWARE_FINGERPRINT) == fp

    def test_skips_hardware_fingerprint_when_none(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        app_config_repo: AppConfigRepository,
    ) -> None:
        """Si fingerprint es None, NO se setea la key (no se guarda string vacío)."""
        onboarding_uc.execute(_data(hardware_fingerprint=None))
        assert app_config_repo.get(KEY_HARDWARE_FINGERPRINT) is None

    def test_marks_onboarding_completed(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        app_config_repo: AppConfigRepository,
    ) -> None:
        assert app_config_repo.is_onboarding_completed() is False
        onboarding_uc.execute(_data())
        assert app_config_repo.is_onboarding_completed() is True

    def test_audits_onboarding_completed(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        audit_log_repo: SQLiteAuditLogRepository,
    ) -> None:
        onboarding_uc.execute(_data())

        recent = audit_log_repo.list_recent(limit=20)
        events = [e.event_type for e in recent]
        assert AuditEventType.ONBOARDING_COMPLETED in events

    def test_weak_password_raises_before_admin_created(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        user_repo: SQLiteUserRepository,
        app_config_repo: AppConfigRepository,
    ) -> None:
        """Si password es débil, primary admin NO se crea, pero CONFIG sí se persistió.

        Trade-off: el wizard puede reintentar sin perder los datos institucionales.
        """
        weak = AdminCreationData(
            username="director", full_name="X", password="123"
        )
        with pytest.raises(WeakPasswordError):
            onboarding_uc.execute(_data(primary_admin=weak))

        # Admin NO creado
        assert user_repo.find_by_username("director") is None
        # Pero CUE sí persistido (decisión documentada)
        assert app_config_repo.get(KEY_CUE) == "540178700"
        # onboarding_completed_at NO seteado (no terminó)
        assert app_config_repo.is_onboarding_completed() is False

    def test_duplicate_username_in_secondary_admin(
        self,
        onboarding_uc: CompleteOnboardingUseCase,
        user_repo: SQLiteUserRepository,
        app_config_repo: AppConfigRepository,
    ) -> None:
        """Si secondary username == primary username, falla en el segundo create."""
        primary = AdminCreationData(
            username="admin", full_name="A", password="strongpass1"
        )
        secondary = AdminCreationData(
            username="admin", full_name="B", password="strongpass2"
        )
        with pytest.raises(UsernameAlreadyExistsError):
            onboarding_uc.execute(
                _data(primary_admin=primary, secondary_admin=secondary)
            )

        # Primer admin SÍ se creó (porque pasó la validación)
        assert user_repo.find_by_username("admin") is not None
        # onboarding_completed_at NO seteado
        assert app_config_repo.is_onboarding_completed() is False
