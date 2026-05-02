"""Use case: ejecutar job de retención de datos.

Responsabilidades:

1. Verificar si toca correr (>= 24h desde la última ejecución registrada
   en ``app_metrics.last_retention_run_at``).
2. Si toca: calcular thresholds en base a la policy, ejecutar las
   purgas atómicas en los repos, registrar resultado.
3. Actualizar ``last_retention_run_at`` solo si el job corrió.

Si NO toca correr (< 24h desde el último), devuelve un RetentionResult
con ``skipped_reason`` poblado y NO actualiza la métrica. Esto es
importante para el patrón "missed jobs": si la app se abre y cierra 5
veces en una hora, solo corre una vez al día.

Si toca correr y crashea a mitad: la métrica NO se actualiza, así que
en la próxima oportunidad se vuelve a intentar. La atomicidad del DELETE
en SQLite garantiza que no quedamos en estado intermedio.

Decisión de scope:
    - El use case ejecuta SECUENCIALMENTE: primero raw, después sync.
      Cada uno es atómico en sí mismo (BEGIN IMMEDIATE).
    - NO usamos una sola transacción para los dos. Si raw purga OK pero
      sync falla, raw queda purgado y sync sin tocar. En el próximo run
      se reintenta sync. Aceptable porque ambos son idempotentes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from yvy.application.ports.time_provider import TimeProvider
from yvy.domain.retention.models import RetentionPolicy, RetentionResult
from yvy.domain.sensor.repository import SensorRepository
from yvy.domain.sync.repository import SyncRepository
from yvy.infrastructure.persistence.app_metrics_repository import (
    AppMetricsRepository,
)

logger = logging.getLogger(__name__)


# Key en app_metrics donde guardamos la última corrida exitosa.
LAST_RUN_KEY = "last_retention_run_at"

# Cooldown entre ejecuciones automáticas. 24h por decisión del plan.
DEFAULT_COOLDOWN = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class RunRetentionJobUseCase:
    """Use case del job de retención.

    Args:
        sensor_repo: implementa ``delete_raw_older_than``.
        sync_repo: implementa ``delete_sent_older_than``.
        metrics_repo: persiste la métrica ``last_retention_run_at``.
        time_provider: para calcular "ahora" testeable.
        policy: política aplicable (default 14 raw / 30 sync).
        cooldown: tiempo mínimo entre ejecuciones automáticas. Default
            24h. ``force=True`` en ``execute()`` lo bypasea.
    """

    sensor_repo: SensorRepository
    sync_repo: SyncRepository
    metrics_repo: AppMetricsRepository
    time_provider: TimeProvider
    policy: RetentionPolicy = field(default_factory=RetentionPolicy.default)
    cooldown: timedelta = DEFAULT_COOLDOWN

    def execute(self, force: bool = False) -> RetentionResult:
        """Ejecuta el job si toca (o si force=True).

        Args:
            force: si True, salta la verificación de cooldown. Útil para
                CLI manual (``yvy retention --force``) y tests.

        Returns:
            ``RetentionResult`` con conteos. ``skipped_reason`` poblado
            si no corrió por cooldown.
        """
        now = self.time_provider.now_utc()

        if not force:
            last_run = self.metrics_repo.get_timestamp(LAST_RUN_KEY)
            if last_run is not None:
                elapsed = now - last_run
                if elapsed < self.cooldown:
                    logger.info(
                        "Retention skipped: %s desde la última corrida (< %s)",
                        elapsed,
                        self.cooldown,
                    )
                    return RetentionResult(
                        raw_deleted=0,
                        sync_archived=0,
                        skipped_reason=f"last run hace {elapsed}, cooldown {self.cooldown}",
                    )

        # Calcular thresholds
        raw_threshold = now - timedelta(days=self.policy.raw_days)
        sync_threshold = now - timedelta(days=self.policy.sync_sent_days)

        logger.info(
            "Retention iniciado: raw < %s (%d días), sync sent < %s (%d días)",
            raw_threshold.isoformat(),
            self.policy.raw_days,
            sync_threshold.isoformat(),
            self.policy.sync_sent_days,
        )

        # Purgas atómicas (cada una en su transacción)
        raw_deleted = self.sensor_repo.delete_raw_older_than(raw_threshold)
        sync_archived = self.sync_repo.delete_sent_older_than(sync_threshold)

        # Registrar la corrida exitosa
        self.metrics_repo.set_timestamp(LAST_RUN_KEY, now)

        logger.info(
            "Retention completado: %d raw borrados, %d sync archivados",
            raw_deleted,
            sync_archived,
        )

        return RetentionResult(
            raw_deleted=raw_deleted,
            sync_archived=sync_archived,
            skipped_reason=None,
        )
