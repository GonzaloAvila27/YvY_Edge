"""Use case: completar onboarding inicial.

Orquesta lo que pasa cuando el wizard llega a la pantalla final:

1. Persiste config institucional (CUE, school_name, station_uuid,
   timezone, hardware_fingerprint si fue capturado).
2. Crea el primer admin (rol superadmin).
3. Crea el segundo admin opcional (rol admin) si fue ingresado.
4. Marca ``onboarding_completed_at`` con timestamp actual.
5. Audit ``ONBOARDING_COMPLETED``.

El use case es **idempotente parcialmente**: si la creación de uno de
los admins falla a mitad, los datos institucionales ya persistidos
quedan, pero ``onboarding_completed_at`` NO se marca. La próxima
ejecución del wizard verá la config existente y debe permitir reintento.

Decisión de error handling: si CUALQUIER paso falla (validación,
duplicate username, etc.), el caller recibe la excepción del use case
de Auth subyacente. El wizard la maneja mostrando mensaje al user y
permitiendo corregir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from yvy.application.use_cases.auth.create_user import CreateUserUseCase
from yvy.domain.auth.enums import AuditEventType, AuditSource, Role
from yvy.domain.auth.models import AuditLogEntry
from yvy.domain.auth.repository import AuditLogRepository

logger = logging.getLogger(__name__)


# Keys de app_config que setea el onboarding.
KEY_CUE = "cue"
KEY_SCHOOL_NAME = "school_name"
KEY_SCHOOL_SHORT_NAME = "school_short_name"
KEY_STATION_UUID = "station_uuid"
KEY_TIMEZONE = "timezone"
KEY_HARDWARE_FINGERPRINT = "hardware_fingerprint"
KEY_ONBOARDING_COMPLETED_AT = "onboarding_completed_at"
KEY_SYNC_SERVER_URL = "sync_server_url"
KEY_STATION_UUID_TEMPORARY = "station_uuid_is_temporary"


@dataclass(frozen=True, slots=True)
class AdminCreationData:
    """Datos para crear un admin durante onboarding."""

    username: str
    full_name: str
    password: str


@dataclass(frozen=True, slots=True)
class OnboardingData:
    """Todo lo que el wizard recolecta antes de llamar al use case."""

    cue: str
    school_name: str
    school_short_name: str
    timezone: str
    primary_admin: AdminCreationData
    secondary_admin: AdminCreationData | None = None
    hardware_fingerprint: str | None = None  # None si no se pudo leer
    # Sync (Fase 9.2) — opcionales: el operador puede saltear este paso
    sync_server_url: str | None = None
    station_credentials: dict | None = None  # dict con station_uuid, key_version, key_hmac_hex


@dataclass(frozen=True, slots=True)
class CompleteOnboardingResult:
    """Resultado del onboarding."""

    station_uuid: str
    primary_admin_id: int
    secondary_admin_id: int | None


@dataclass(frozen=True, slots=True)
class CompleteOnboardingUseCase:
    """Orquesta el flujo completo de onboarding."""

    create_user_uc: CreateUserUseCase
    audit_repo: AuditLogRepository
    # AppConfigRepository inyectado pero sin tipo explícito en domain
    # (es de infrastructure). Se valida estructuralmente.
    app_config_repo: object
    # Raíz del proyecto para escribir data/station_credentials.json
    credentials_root: Path = field(default_factory=Path.cwd)

    def execute(self, data: OnboardingData) -> CompleteOnboardingResult:
        """Ejecuta los 5 pasos del onboarding.

        Si falla la creación del primer admin (ej. password débil), nada
        se persiste de admins; pero los campos institucionales sí se
        persisten antes. El wizard puede volver a llamar para completar.

        Returns:
            CompleteOnboardingResult con station_uuid generado y los ids.
        """
        # 1. Persistir config institucional (incluso si admins fallan después)
        # UUID definitivo: viene de credentials si se proveyeron; aleatorio si no.
        if data.station_credentials and "station_uuid" in data.station_credentials:
            station_uuid = str(data.station_credentials["station_uuid"])
        else:
            station_uuid = str(uuid4())
        self._persist_config(data, station_uuid)

        # 2. Crear primer admin (siempre superadmin)
        primary = self.create_user_uc.execute(
            username=data.primary_admin.username,
            full_name=data.primary_admin.full_name,
            password=data.primary_admin.password,
            role=Role.SUPERADMIN,
        )
        assert primary.id is not None

        # 3. Crear segundo admin si fue ingresado (rol admin)
        secondary_id: int | None = None
        if data.secondary_admin is not None:
            secondary = self.create_user_uc.execute(
                username=data.secondary_admin.username,
                full_name=data.secondary_admin.full_name,
                password=data.secondary_admin.password,
                role=Role.ADMIN,
            )
            secondary_id = secondary.id

        # 4. Marcar onboarding completado
        now_iso = datetime.now(timezone.utc).isoformat()
        self.app_config_repo.set(KEY_ONBOARDING_COMPLETED_AT, now_iso)  # type: ignore[attr-defined]

        # 5. Audit
        self.audit_repo.append(
            AuditLogEntry(
                event_type=AuditEventType.ONBOARDING_COMPLETED,
                source=AuditSource.UI,
                user_id=primary.id,
                username=primary.username,
                role=Role.SUPERADMIN,
                metadata={
                    "station_uuid": station_uuid,
                    "cue": data.cue,
                    "school_name": data.school_name,
                    "primary_admin_id": primary.id,
                    "secondary_admin_id": secondary_id,
                    "has_hardware_fingerprint": (
                        data.hardware_fingerprint is not None
                    ),
                },
            )
        )

        logger.info(
            "Onboarding completado: station=%s, school=%s, admins=%d",
            station_uuid,
            data.school_name,
            2 if secondary_id else 1,
        )

        return CompleteOnboardingResult(
            station_uuid=station_uuid,
            primary_admin_id=primary.id,
            secondary_admin_id=secondary_id,
        )

    def _persist_config(self, data: OnboardingData, station_uuid: str) -> None:
        """Setea las keys de identidad institucional en app_config."""
        repo = self.app_config_repo
        repo.set(KEY_CUE, data.cue)  # type: ignore[attr-defined]
        repo.set(KEY_SCHOOL_NAME, data.school_name)  # type: ignore[attr-defined]
        repo.set(KEY_SCHOOL_SHORT_NAME, data.school_short_name)  # type: ignore[attr-defined]
        repo.set(KEY_STATION_UUID, station_uuid)  # type: ignore[attr-defined]
        repo.set(KEY_TIMEZONE, data.timezone)  # type: ignore[attr-defined]
        if data.hardware_fingerprint is not None:
            repo.set(KEY_HARDWARE_FINGERPRINT, data.hardware_fingerprint)  # type: ignore[attr-defined]

        # Sync (Fase 9.2)
        if data.sync_server_url:
            repo.set(KEY_SYNC_SERVER_URL, data.sync_server_url)  # type: ignore[attr-defined]
        if data.station_credentials:
            self._write_credentials(data.station_credentials)
            # UUID definitivo viene de credentials, no de generación aleatoria
            repo.set(KEY_STATION_UUID, data.station_credentials["station_uuid"])  # type: ignore[attr-defined]
            # Limpiar flag temporal si estaba seteado
            repo.delete(KEY_STATION_UUID_TEMPORARY)  # type: ignore[attr-defined]

    def _write_credentials(self, creds: dict) -> None:
        """Escribe data/station_credentials.json en el filesystem."""
        creds_dir = self.credentials_root / "data"
        creds_dir.mkdir(parents=True, exist_ok=True)
        creds_path = creds_dir / "station_credentials.json"
        creds_path.write_text(
            json.dumps(creds, indent=2), encoding="utf-8"
        )
        logger.info("station_credentials.json escrito en %s", creds_path)
