# Exportación de datos: procesado vs crudo

YVY ofrece **dos tipos de export** distintos. Es importante elegir el correcto según el destinatario.

## Export procesado (`export.csv`)

**Para qué**: uso interno del IEA. Informes a directivos, comparativas históricas, análisis básico.

**Qué contiene**: una fila por observación con todas las métricas **ya parseadas** y validadas:

- Timestamps (UTC y local).
- Temperatura (interior y exterior), humedad, presión, viento, lluvia, UV, radiación.
- Flag de validación.

**Quién puede descargarlo**: cualquier usuario con rol **Profesor**, **Admin** o **Superadmin** activo.

**Cuándo usarlo**:

- Vas a presentar un informe de zafra a la dirección.
- Necesitás analizar el clima de los últimos meses para planificar siembra.
- Querés comparar este año con el anterior.

## Export crudo (`export_raw.csv`)

**Para qué**: envío a instituciones externas que necesitan los **datos sin procesar**, típicamente la tecnicatura asociada al proyecto YVY para uso académico.

**Qué contiene**: una fila por lectura del sensor con la columna `payload` que guarda el **JSON literal** que mandó el sensor, sin parsear.

**Quién puede descargarlo**: solo usuarios con el flag **"Permitir export raw"** explícitamente activado por un administrador.

**Cuándo usarlo**:

- La tecnicatura te pidió datos para sus prácticas de EDA.
- Necesitás compartir lecturas crudas para análisis especializado.
- **NO uses este export para informes internos**: el formato no es legible sin procesar.

## Ventana de tiempo

Ambos exports usan el **filtro de fechas** que está arriba de la tabla en la vista de Datos. Por defecto: últimos 7 días. Si necesitás otro rango, ajustalo antes de exportar.

## El export queda registrado

Cada export queda **auditado** con tu usuario, la cantidad de filas y la ventana de fechas. Esto se ve en la sección **Logs**.

---

*Contenido provisorio — pendiente de revisión.*
