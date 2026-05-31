"""Repositorio del subdominio sync (interfaz)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Protocol
from uuid import UUID

from yvy.domain.sync.enums import EntityType, SyncStatus
from yvy.domain.sync.models import SyncJob


class SyncRepository(Protocol):
    """Interfaz para encolar items de sync.

    Expone:
    - **Escritura**: ``enqueue``.
    - **Lookups individuales**: ``find_by_event_id``.
    - **Counts y listados** (Fase 4.5+): ``count``, ``count_by_status``,
      ``count_sent_today``, ``list_recent``. Necesarios para la UI de
      sync status (KPIs + tabla de eventos).

    El claim atómico, retry, archive vienen en Fase 9 (sync agent).

    Decisión arquitectónica (Fase 4.5): los métodos read-only viven en
    el mismo Protocol que los de escritura. NO se usa CQRS.
    Ver ``yvy_FASE4_RESUMEN.md`` sección "Decisión arquitectónica" para
    el razonamiento completo.
    """

    # ─── Escritura ───────────────────────────────────────────────────────

    def enqueue(self, job: SyncJob) -> int:
        """Encola un SyncJob. Devuelve id autoincrement.

        Si ya existía una fila con el mismo ``event_id``, devuelve el id
        existente sin re-encolar (idempotencia).
        """
        ...

    # ─── Lookups individuales ────────────────────────────────────────────

    def find_by_event_id(self, event_id: UUID) -> SyncJob | None:
        """Busca un SyncJob por su event_id. None si no existe."""
        ...

    def count(self) -> int:
        """Cantidad total de jobs en la cola."""
        ...

    # ─── Listados y agregaciones (Fase 4.5) ─────────────────────────────

    def list_recent(
        self,
        limit: int = 50,
        status_filter: SyncStatus | None = None,
        before_id: int | None = None,
    ) -> list[SyncJob]:
        """Lista jobs ordenados por id DESC (más recientes primero).

        Args:
            limit: máximo de resultados. Cap interno a 200 por seguridad.
            status_filter: si se provee, filtra por ese status.
            before_id: paginación cursor-based. Si se provee, devuelve
                jobs con ``id < before_id``. Para obtener la página
                siguiente, pasar el id mínimo de la página actual.

        Returns:
            Lista de SyncJob en orden descendente por id. Lista vacía si
            no hay coincidencias.

        Notes:
            Cursor-based en lugar de offset porque sync_queue recibe
            inserts continuamente (cada lectura live + cada catchup).
            Offset rompe paginación frente a inserts concurrentes:
            filas vistas en página N reaparecen en página N+1.
        """
        ...

    def count_by_status(self) -> dict[SyncStatus, int]:
        """Cuenta jobs agrupados por status.

        Returns:
            Diccionario con las 4 keys de SyncStatus siempre presentes,
            valor 0 si no hay jobs en ese status. Esto permite a la UI
            renderizar los 4 KPIs sin lógica de defaulting.

        Implementación esperada: un único ``SELECT status, COUNT(*) ...
        GROUP BY status`` + relleno de keys faltantes en Python.
        """
        ...

    def count_sent_today(self, tz: tzinfo) -> int:
        """Cuenta jobs marcados ``sent`` del día local actual.

        "Día local actual" se interpreta como el intervalo
        ``[00:00 local hoy, 00:00 local mañana)``.

        Args:
            tz: zona horaria local (típicamente
                ``zoneinfo.ZoneInfo('America/Argentina/Cordoba')``). Se
                pasa explícito para no acoplar el repo a una zona fija
                ni al tz del sistema operativo.

        Returns:
            Cantidad de jobs con status='sent' cuyo created_at,
            convertido a la zona ``tz``, cae en el día local actual.

        Notes:
            Jobs con created_at en el futuro (ej. clock skew del sensor
            o NTP corrigiendo hacia atrás) NO entran al conteo de hoy.
            Quedan invisibles hasta que el día local los alcance.

            Implementación esperada: calcular en Python los UTC
            equivalentes al "00:00 local hoy" y "00:00 local mañana" y
            pasarlos como parámetros a la query como strings ISO. NO usar
            ``date(created_at, 'localtime')`` que depende del tz del SO.
        """
        ...

    # ─── Sync agent (Fase 9.2) ──────────────────────────────────────────

    def claim_next_pending(
        self,
        *,
        now_utc: datetime,
        supported_entity_types: set[EntityType],
    ) -> tuple[int, SyncJob] | None:
        """Reserva atómicamente el próximo job pending elegible.

        Filtra por status='pending', entity_type IN supported_entity_types,
        y next_retry_at IS NULL OR next_retry_at <= now_utc.

        Returns:
            (job_id, SyncJob) si se reservó un job, None si no hay elegibles.
        """
        ...

    def mark_sent(
        self,
        *,
        job_id: int,
        was_duplicate: bool,
        sent_at_utc: datetime,
    ) -> None:
        """Marca un job como enviado ('sent') o duplicado ('duplicate').

        Libera el lease (claimed_at = NULL). NO incrementa attempt_count.
        """
        ...

    def mark_failed(
        self,
        *,
        job_id: int,
        attempt_count: int,
        last_error: str,
        next_retry_at: datetime | None,
        permanent: bool = False,
    ) -> None:
        """Marca un job como fallido, transient o permanente.

        permanent=True → status='error' (DLQ, no se reintenta).
        permanent=False → status='pending', next_retry_at programado.
        Libera el lease (claimed_at = NULL).
        """
        ...

    def reap_zombies(
        self,
        *,
        now_utc: datetime,
        lease_timeout_seconds: int,
    ) -> int:
        """Rescata jobs zombie (status='sending' con claimed_at vencido).

        Resetea status='pending' y claimed_at=NULL. NO toca attempt_count
        ni last_error (el zombie es fallo de proceso, no de envío).

        Returns:
            Count de filas rescatadas.
        """
        ...

    # ─── Retención (Fase 5) ──────────────────────────────────────────────

    def delete_sent_older_than(self, threshold_utc: datetime) -> int:
        """Borra jobs con status='sent' y last_attempt < threshold_utc.

        Atómica: un único DELETE en una transacción.

        Args:
            threshold_utc: timestamp UTC tz-aware. Jobs sent con
                ``last_attempt`` estrictamente menor se borran.

        Returns:
            Cantidad de jobs borrados.

        Notes:
            CRÍTICO: solo toca jobs con status='sent'. Jobs en status
            pending/sending/error NUNCA se purgan por este método. Si
            una IEA está semanas sin internet, los pending acumulados
            sobreviven indefinidamente.

            El umbral se compara contra ``last_attempt`` (cuando fue
            efectivamente confirmado al server), NO contra
            ``created_at``. Esto significa que un job que se envió ayer
            tras estar 2 meses pendiente se conserva 30 días desde ayer,
            no se purga inmediatamente.

            Si ``last_attempt`` es NULL (caso teórico raro: un job
            marcado sent sin intentos registrados), el job NO se purga
            por este método. Es defensivo: ante data inconsistente,
            no borrar.
        """
        ...
