---
language: es
---

# Política de retención

YVY mantiene la base de datos local **acotada** para que no crezca sin límite. Esto se hace con un **job de retención** que corre automáticamente y purga datos viejos según una política configurable.

## Qué se borra y qué NO

**SE borra automáticamente**:

- **Lecturas crudas (`sensor_raw`)**: el JSON literal que mandó el sensor. Default: borradas después de **14 días**.
- **Cola de sync ya enviada**: registros marcados como "enviados al servidor central". Default: borrados **30 días** después de envío.

**NUNCA se borra automáticamente**:

- **Observaciones procesadas (`sensor_data`)**: las métricas validadas. Estas se conservan **indefinidamente** por gobernanza institucional.
- **Observaciones manuales**: granizo, helada, etc. cargadas por usuarios.
- **Cola de sync NO enviada**: si una IEA está sin internet por meses, los registros pendientes no se purgan. Esperan al reconectarse.
- **Logs de auditoría**: eventos de seguridad y trazabilidad.
- **Usuarios**: solo se desactivan, nunca se borran.

## Cómo configurar

1. Menú lateral → **Configuración**.
2. Ajustá los días con los Spinbox.
3. Click en **Guardar configuración**.

Los cambios **NO se aplican inmediatamente**. Se aplican en la próxima ejecución del job de mantenimiento (próximo arranque del sistema o cada 24 hs).

Si querés aplicar inmediato (solo Superadmin), usá el botón rojo **Forzar retención manual**. Asegurate de haber guardado primero.

## Por qué esta política

El sensor genera **~30 lecturas por hora**. En un año, son ~260.000 filas en `sensor_raw`. Cada una tiene un JSON de varios KB. Sin retención, la base llega a varios GB y se vuelve lenta.

Las **observaciones procesadas** son ~30/hora también pero ocupan poco (es solo la fila parseada, sin el JSON completo). Por eso se pueden conservar siempre.

---

*Contenido provisorio — pendiente de revisión técnica.*
