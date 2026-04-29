"""Controllers: mediadores entre views y use cases.

Decisión Fase 4: el SyncStatusView con su botón de catchup recovery
requiere métodos de listado (list_by_status) que el SyncRepository
actual NO expone (solo enqueue/find/count en Fase 2/3).

Antes de implementar `sync_controller.py`, hay que decidir:
  (a) Extender Protocol SyncRepository con list_recent + count_by_status.
  (b) Crear un read-model separado (SyncQueueQuery).

Recomendación: (a) — más simple. Por ahora, esta carpeta queda como
placeholder. El catchup_modal y sync_status_view vendrán en Fase 4.5
cuando se cierre esta decisión.
"""
