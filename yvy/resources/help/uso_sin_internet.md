---
language: es
---

# Cuando no hay internet

YVY está diseñado para **funcionar normalmente sin internet**. Esto es deliberado: las escuelas rurales tienen conectividad intermitente y el sistema no puede dejar de funcionar por eso.

## Qué SÍ funciona sin internet

- Recolección de datos del sensor.
- Carga manual de observaciones.
- Visualización de Datos, Dashboard, Logs.
- Login y gestión de usuarios.
- Exportación de CSVs.

## Qué NO funciona

- **Sincronización con el servidor central**: las observaciones quedan **acumuladas localmente** en una cola de envío.
- Las funciones que dependen de servicios externos (no aplica en Fase actual).

## Qué pasa cuando vuelve internet

YVY detecta automáticamente la conexión y **envía toda la cola acumulada** al servidor central. No tenés que hacer nada manual.

El indicador de **Sync** en la barra superior cambia:

- **Rojo / ámbar**: cola acumulada, sin enviar.
- **Verde**: todo enviado, al día.

## Cuánto tiempo puede aguantar

La base local guarda las lecturas crudas durante **14 días por defecto** (configurable). Las observaciones procesadas y manuales se guardan **siempre** sin límite. En la práctica, una IEA puede estar sin internet **semanas o meses** y al reconectarse el sistema sincroniza todo.

---

*Contenido provisorio — pendiente de revisión técnica.*
