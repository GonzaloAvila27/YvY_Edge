"""Daemon threads de background.

Implementaciones:
- ``sensor_collector.SensorCollectorDaemon`` — captura periódica del sensor WH1081.
- SyncAgent — pendiente (Fase 9+).
- MaintenanceJob — pendiente (Fase 9+).
"""

from yvy.infrastructure.scheduling.sensor_collector import SensorCollectorDaemon

__all__ = ["SensorCollectorDaemon"]
