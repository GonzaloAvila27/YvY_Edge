"""Use case: actualizar la política de retención.

Persiste valores nuevos en app_metrics. NO dispara retención inmediata:
los cambios se aplican cuando el job de retention corre la próxima vez
(en cada arranque o tic 24hs), porque ``RetentionPolicy.from_app_metrics()``
relee los valores en cada ejecución.

Decisión cerrada: si el admin cambia raw_days de 14 a 7, no perdemos
los 7 días intermedios automáticamente. Hay que clickear "Forzar
retention" explícitamente para aplicar inmediato.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from yvy.domain.retention.models import RetentionPolicy

logger = logging.getLogger(__name__)


KEY_RAW_DAYS = "retention_raw_days"
KEY_SYNC_SENT_DAYS = "retention_sync_sent_days"


@dataclass(frozen=True, slots=True)
class UpdateRetentionPolicyUseCase:
    """Persiste nueva política. Validación delegada al value object."""

    metrics_repo: object  # AppMetricsRepository

    def execute(self, *, raw_days: int, sync_sent_days: int) -> RetentionPolicy:
        """Valida y persiste. Devuelve la policy resultante.

        Raises:
            ValueError: si los valores no pasan la validación de
                ``RetentionPolicy`` (rangos, etc.).
        """
        # Validamos construyendo el value object — si hay problema, levanta
        policy = RetentionPolicy(raw_days=raw_days, sync_sent_days=sync_sent_days)

        self.metrics_repo.set_counter(KEY_RAW_DAYS, raw_days)  # type: ignore[attr-defined]
        self.metrics_repo.set_counter(KEY_SYNC_SENT_DAYS, sync_sent_days)  # type: ignore[attr-defined]

        logger.info(
            "RetentionPolicy actualizada: raw=%d días, sync_sent=%d días",
            raw_days,
            sync_sent_days,
        )
        return policy
