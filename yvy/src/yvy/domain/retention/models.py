"""Modelos del dominio de retención de datos.

El job de retención tiene dos targets distintos con políticas distintas:

1. ``sensor_raw``: filas crudas del buffer de pywws. Útiles para rescate
   de datos para tecnicatura (descarga manual). Se conservan N días
   (default 14). Después se purgan.

2. ``sync_queue`` con status='sent': jobs ya confirmados al servidor
   central. Se conservan N días desde ``last_attempt`` (default 30) y
   se purgan. El conteo se hace sobre ``last_attempt``, NO sobre
   ``created_at``, porque "30 días desde que se envió" es lo que
   importa, no "30 días desde que se creó la fila local".

GARANTÍAS DE PERSISTENCIA (gobernanza de datos institucional):

- ``sensor_data`` (lecturas parseadas): NUNCA se purga por el job de
  retención. Persiste indefinidamente en el almacenamiento local de
  la IEA. Esto es un requisito institucional: las escuelas deben
  conservar la serie histórica de observaciones aunque se haya
  sincronizado al server central.

- ``sync_queue`` con status != 'sent' (pending/sending/error): NUNCA
  se purga por el job de retención. Si una IEA está dos meses sin
  internet, los pending sobreviven hasta que el sync agent los
  procese. Es responsabilidad del sync agent (Fase 9), no de
  retention, decidir qué hacer con jobs viejos en error.

- Resultados de catchup recovery, métricas del sistema, configuración
  de usuarios, comentarios empíricos, etc.: fuera del scope de
  retention.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Política de retención configurable por IEA.

    Attributes:
        raw_days: cantidad de días que se conservan filas en
            ``sensor_raw`` desde su ``received_at``. Filas más antiguas
            se purgan.
        sync_sent_days: cantidad de días que se conservan jobs en
            ``sync_queue`` con status='sent' desde su ``last_attempt``.
            Jobs más antiguos se purgan.

    Notes:
        Ambos valores deben ser estrictamente positivos. ``0`` significaría
        "purgar todo" lo que es destructivo y debe ser opt-in explícito;
        si en algún futuro caso de uso se necesita, agregar un método
        ``purge_all()`` separado en lugar de aceptar 0 acá.
    """

    raw_days: int
    sync_sent_days: int

    def __post_init__(self) -> None:
        if self.raw_days <= 0:
            raise ValueError(
                f"raw_days debe ser > 0, recibido {self.raw_days}. "
                f"Para purgar todo, usar un método dedicado."
            )
        if self.sync_sent_days <= 0:
            raise ValueError(
                f"sync_sent_days debe ser > 0, recibido {self.sync_sent_days}."
            )

    @classmethod
    def default(cls) -> RetentionPolicy:
        """Política por defecto: 14 días de raw, 30 días de sync sent."""
        return cls(raw_days=14, sync_sent_days=30)

    @classmethod
    def from_app_metrics(cls, metrics_repo: object) -> RetentionPolicy:
        """Lee la policy desde ``app_metrics``, cae a default si no existe.

        Permite que la UI de admin (Fase 7) escriba ``retention_raw_days``
        y ``retention_sync_sent_days`` sin requerir migraciones.

        Args:
            metrics_repo: instancia de ``AppMetricsRepository`` (no se
                tipa explícito acá para evitar import circular
                domain → infrastructure).

        Returns:
            Policy con los valores leídos, o ``default()`` si las keys
            no existen o tienen valores inválidos.
        """
        try:
            raw = metrics_repo.get_counter("retention_raw_days")  # type: ignore[attr-defined]
            sync = metrics_repo.get_counter("retention_sync_sent_days")  # type: ignore[attr-defined]
        except Exception:
            return cls.default()

        # get_counter devuelve 0 si la key no existe. Caemos a default.
        if raw <= 0 or sync <= 0:
            return cls.default()

        try:
            return cls(raw_days=raw, sync_sent_days=sync)
        except ValueError:
            return cls.default()


@dataclass(frozen=True, slots=True)
class RetentionResult:
    """Resultado de una corrida del job de retención.

    Attributes:
        raw_deleted: cantidad de filas borradas de ``sensor_raw``.
        sync_archived: cantidad de filas borradas de ``sync_queue``
            (todas con status='sent'). Se llama "archived" porque
            conceptualmente fueron archivadas al server central antes
            de borrarse local.
        skipped_reason: si el job no corrió, motivo. None si corrió.
            Usado por el caller para distinguir "0 filas porque la DB
            estaba limpia" de "0 filas porque no toca correr aún".
    """

    raw_deleted: int
    sync_archived: int
    skipped_reason: str | None = None

    @property
    def did_run(self) -> bool:
        return self.skipped_reason is None
