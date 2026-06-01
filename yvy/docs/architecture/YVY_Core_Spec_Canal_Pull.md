# YVY — Canal Core → Edge (Spec del contrato)

**Documento:** especificación del contrato HTTP entre YVY Core y YVY Edge para sincronización descendente (pull).
**Versión:** 1.0
**Estado:** propuesta para implementación coordinada.
**Audiencia:** equipo que implementa YVY Core.
**Autor:** Gonzalo Rubens Avila (peer review IA).

---

## 1. Contexto y propósito

YVY hoy tiene un flujo unidireccional Edge → Core: los nodos Edge envían observaciones, eventos y readings al servidor central mediante endpoints de ingest firmados con HMAC.

Este documento especifica el **canal inverso Core → Edge**: cómo YVY Core notifica a cada nodo sobre novedades disponibles, empezando por **actualizaciones de software**.

El alcance de esta primera versión del canal es deliberadamente acotado: solo permite que Edge consulte si hay versiones nuevas de software y obtenga la metadata para descargarlas. No incluye la entrega del binario en sí (esa es una operación separada documentada en sección 7) ni otras categorías de contenido (feed editorial, alertas, configuración de dashboard, etc.) que se sumarán en fases posteriores reutilizando el mismo canal.

**Motivación operativa:** las IEAs del piloto están a 60+ km de la sede del proyecto. Cualquier cambio que requiera viaje físico cuesta medio día de trabajo y traslado sin viático. Disponer del canal de updates por red elimina la necesidad de viajar para instalar correcciones, mejoras o parches de seguridad.

---

## 2. Principios de diseño

Cinco principios orientan las decisiones del contrato:

**Principio 1: un solo endpoint de pull, extensible.** La primera versión solo informa de updates, pero el contrato del response está estructurado para agregar categorías (feed, alerts, dashboard, assistant_context) sin romper Edges existentes.

**Principio 2: versionado global monotónico.** Core mantiene un contador `sync_version` que incrementa con cada cambio distribuible. Edge consulta "qué cambió desde la versión N" y Core responde con todo lo nuevo.

**Principio 3: piggyback sobre ingest.** Cada respuesta del Edge a un POST de ingest incluye el `sync_version` actual del server. Edge dispara el pull solo cuando detecta un valor mayor al que tiene cacheado. Esto evita polling activo y reduce tráfico.

**Principio 4: metadata vs binarios separados.** El endpoint de pull retorna solo metadata (URLs, hashes, tamaños). La descarga del binario es operación separada con su propio endpoint, su propia política de timeout y su propio mecanismo de verificación.

**Principio 5: distribución acumulativa.** No hay updates incrementales (1.0 → 1.1 → 1.2 → 1.3). Cada release publicado en Core es un paquete completo y autocontenido. Un Edge que está en 1.0 y consulta cuando Core publicó 1.3 recibe directamente metadata de 1.3, sin pasar por las versiones intermedias. Esto simplifica la lógica de update en Edge y elimina la necesidad de cadenas de migración condicionales.

---

## 3. Autenticación

Toda comunicación Core ↔ Edge usa la misma identidad criptográfica establecida en el sync push:

- **Identificador del nodo:** `station_uuid` (UUID v4 asignado en provisioning del Edge desde Core).
- **Firma:** HMAC-SHA256 con la `station_key` correspondiente al `station_uuid`, con versionado de key (`key_version`).
- **Algoritmo de firma idéntico al de ingest:** sobre el canonical JSON del request, con `nonce` y `sent_at_utc` para evitar replay.

**Decisión:** se reutiliza la HMAC key del sync push para no introducir un segundo plano de identidad. Esto significa que comprometer una key compromete tanto el envío de datos como la recepción de updates. Aceptable para el piloto. Cuando se rote keys (planeado post-piloto), se hace para ambos canales al mismo tiempo.

**Decisión:** el CUE escolar **no se usa para autenticación**. Puede incluirse como dato informativo en logs server-side (loguear "request from station X, CUE 540178700") pero el control de acceso es exclusivamente por `station_uuid` + firma HMAC.

---

## 4. Endpoint principal: `GET /api/v1/edge/sync`

### 4.1 Request

```
GET /api/v1/edge/sync HTTP/1.1
Host: <yvy-core-host>
Authorization: HMAC <signature>
X-Station-UUID: <station_uuid>
X-Key-Version: <key_version int>
X-Edge-Version: <edge_software_version, ej. "0.9.2">
X-Last-Sync-Version: <int, último sync_version conocido por el Edge>
X-Nonce: <32 chars random>
X-Sent-At-UTC: <ISO 8601 timestamp>
```

**Notas:**

- `X-Last-Sync-Version` puede ser `0` si es la primera consulta del Edge (fresh install).
- `X-Edge-Version` es informativo para que Core sepa qué versión está corriendo y pueda decidir si servir un update incremental o un paquete bootstrap completo.
- No hay body en el request. El método es GET.
- La firma HMAC se calcula sobre el canonical JSON de los headers relevantes en orden alfabético. Especificación exacta de canonicalización: ver módulo `canonical_json.py` del proyecto YVY (compartido entre Edge y Core).

### 4.2 Response 200 — Sin novedades

```json
{
  "sync_version": 41,
  "updates": {
    "available": false
  }
}
```

El Edge interpreta esto como "estoy al día" y persiste localmente `last_sync_version = 41`. La próxima consulta usará ese valor.

### 4.3 Response 200 — Update disponible

```json
{
  "sync_version": 42,
  "updates": {
    "available": true,
    "edge_version": "0.9.3",
    "package_url": "/api/v1/edge/updates/0.9.3.tar.gz",
    "package_sha256": "abcd1234ef56...",
    "package_size_bytes": 45200000,
    "released_at": "2026-06-15T10:00:00Z",
    "min_edge_version": "0.9.0",
    "notes": "Fix de timeout USB en sesiones largas. Mejora del dashboard. Migración de schema v14."
  }
}
```

**Campos del bloque `updates`:**

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `available` | bool | Sí | Si hay una versión más reciente que `X-Edge-Version` |
| `edge_version` | string semver | Si available=true | Versión disponible |
| `package_url` | string | Si available=true | Path absoluto del binario en el server (relativo al host) |
| `package_sha256` | string hex 64 chars | Si available=true | Hash SHA-256 del .tar.gz para verificación de integridad |
| `package_size_bytes` | int | Si available=true | Tamaño exacto para barra de progreso y validación pre-descarga |
| `released_at` | string ISO 8601 | Si available=true | Cuándo se publicó en Core |
| `min_edge_version` | string semver | Si available=true | Versión mínima de Edge desde la cual este update es seguro de aplicar. Si el Edge está por debajo, ignorar y esperar update intermedio |
| `notes` | string | Opcional | Notas humanas para el operador, mostradas en UI |

### 4.4 Estructura del response: claves extensibles

El response actual solo tiene la clave `updates`. La estructura está preparada para crecer:

```json
{
  "sync_version": 42,
  "updates": { ... },
  "alerts": { ... },          // Fase 12+
  "feed": { ... },            // Fase 12+
  "dashboard": { ... },       // Fase 13+
  "assistant": { ... },       // Fase 13+
  "future_category": { ... }  // cualquier extensión futura
}
```

**Regla para Edges:** un Edge debe ignorar silenciosamente claves del response que no entiende. Esto permite que Core agregue categorías sin romper Edges en versiones anteriores.

**Regla para Core:** una clave que aún no tiene contenido se omite (no se incluye con valor vacío). Un Edge nuevo va a interpretar "ausencia de clave" como "no aplica todavía" sin necesidad de chequear contenido.

### 4.5 Respuestas de error

| Código | Cuándo | Acción del Edge |
|---|---|---|
| `401 Unauthorized` | Firma HMAC inválida o key revocada | Log error, NO reintentar inmediatamente, latchear hasta próximo arranque o intervención manual |
| `403 Forbidden` | station_uuid conocido pero deshabilitado en Core | Igual a 401 |
| `404 Not Found` | station_uuid desconocido | Log error con instrucción "verificar credentials" |
| `429 Too Many Requests` | Rate limit excedido | Retry con backoff según header `Retry-After` |
| `500 Internal Server Error` | Error transitorio del server | Retry en próximo trigger (sin retry inmediato) |
| `503 Service Unavailable` | Core en mantenimiento | Retry en próximo trigger |

**El Edge nunca reintenta inmediatamente al recibir error.** Toda recuperación es lazy: en el próximo trigger natural (piggyback o tick periódico) se vuelve a intentar.

---

## 5. Piggyback: indicador en respuestas de ingest

Para evitar polling activo, cada respuesta de los endpoints de ingest existentes (`/api/v1/ingest/sensor`, `/observation`, `/event`) debe incluir un header indicando la versión actual de sync de Core:

```
HTTP/1.1 200 OK
Content-Type: application/json
X-Server-Sync-Version: 42

{
  "accepted": true,
  "was_duplicate": false,
  "ingest_result": "inserted"
}
```

**Lógica del Edge:**

- Cada response de ingest se inspecciona en busca del header `X-Server-Sync-Version`.
- Si el valor del header es mayor que el `last_sync_version` cacheado localmente, el Edge dispara internamente un trigger para que el `UpdateCheckerDaemon` consulte `/api/v1/edge/sync`.
- El sync agent del Edge no espera al pull; sigue su loop normalmente.

**Por qué header y no body:**

El body del ingest response ya tiene semántica específica de la operación (`accepted`, `was_duplicate`, `ingest_result`). Agregar `server_sync_version` ahí mezcla planos. Los headers son ortogonales al body y modelan correctamente "esto es metadata transversal del estado del server".

**Sobre cadencia natural:** dado que el Edge hace POST de ingest cada ~48 segundos (al ritmo de captura del sensor), el Edge recibe el header con esa misma frecuencia. Esto significa que cualquier actualización publicada en Core se detecta en el Edge dentro de los próximos 48 segundos sin polling explícito.

---

## 6. Versionado global `sync_version`

### 6.1 Semántica

`sync_version` es un entero monotónico creciente mantenido por Core. Se incrementa cada vez que se publica un cambio distribuible a los Edges. Ejemplos de eventos que incrementan la versión:

- Publicación de un nuevo release de Edge (afecta `updates`).
- (Futuro) Publicación de un nuevo item en feed editorial.
- (Futuro) Emisión de una alerta operativa.
- (Futuro) Cambio en configuración de dashboard.

**Atomicidad:** la asignación de `sync_version` debe ser atómica para garantizar monotonía. Implementación sugerida: secuencia de PostgreSQL o tabla dedicada con `UPDATE ... RETURNING` en una transacción.

**Persistencia:** el valor vive en Core. Cada Edge cachea localmente el último valor conocido en su propio `app_config`.

### 6.2 No reinicios

`sync_version` no se reinicia. Crece indefinidamente. Para volumen del proyecto (decenas o cientos de cambios por año), un int64 alcanza para millones de años.

### 6.3 Snapshot delivery (distribución acumulativa)

Cuando un Edge consulta con `X-Last-Sync-Version: 38` y la versión actual de Core es `42`, el response devuelve el estado actual de cada categoría, no un diff acumulativo de los cambios 39, 40, 41 y 42.

**Concretamente para updates:**

- Core no envía "entre 38 y 42 hubo 4 releases publicados".
- Core envía: "la versión actualmente recomendada para tu Edge es 0.9.3, descargá desde aquí".
- Si entre la 38 y la 42 hubo varios releases intermedios (0.9.0, 0.9.1, 0.9.2 ya disponibles), eso es invisible al Edge. Solo le interesa la más reciente compatible.

**Por qué snapshot vs diff:**

- Más simple de implementar en Core y Edge.
- El paquete `.tar.gz` ya es autocontenido: contiene el árbol completo del software más las migraciones desde la versión anterior compatible. No hay diffs entre paquetes.
- Si un Edge perdió 3 updates intermedios (por estar offline o por bug), el siguiente request al canal le entrega directo el más reciente, sin tener que aplicar la cadena de updates intermedios.
- Las migraciones de schema son forward-only y acumulativas (ya parte de la arquitectura YVY). Aplicar la cadena v8 → v9 → v10 → v11 → v12 → v13 al instalar 0.9.3 sobre un Edge 0.8.0 funciona naturalmente porque el instalador del paquete corre todas las migraciones pendientes en orden.

**Esto debe quedar claramente documentado en Core** para evitar la tentación de implementar entrega incremental.

---

## 7. Endpoint de descarga: `GET /api/v1/edge/updates/<filename>`

### 7.1 Request

```
GET /api/v1/edge/updates/0.9.3.tar.gz HTTP/1.1
Host: <yvy-core-host>
Authorization: HMAC <signature>
X-Station-UUID: <station_uuid>
X-Key-Version: <key_version int>
X-Nonce: <32 chars random>
X-Sent-At-UTC: <ISO 8601 timestamp>
```

Misma autenticación que el endpoint de pull. El path del archivo viene del campo `package_url` del response previo.

### 7.2 Response 200

```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 45200000
Content-Disposition: attachment; filename="0.9.3.tar.gz"
X-Package-SHA256: abcd1234ef56...

<binary bytes>
```

**Decisión:** la descarga es streaming directo del binario. No se envuelve en JSON, no se base64-codifica.

### 7.3 Por qué endpoint separado

- **Timeouts distintos.** El pull metadata es respuesta corta (<1KB), timeout puede ser 10 segundos. La descarga de un .tar.gz de 40+ MB en conectividad IEA puede tardar varios minutos. Mezclarlos en un solo endpoint requiere lógica de timeout adaptativa innecesaria.
- **Cache HTTP estándar.** El binario puede beneficiarse de caching agresivo (es inmutable: 0.9.3.tar.gz siempre tiene el mismo contenido). Headers como `Cache-Control: public, immutable, max-age=31536000` aplican naturalmente. El endpoint de pull NO debe cachearse.
- **Idempotencia natural.** Si una descarga se corta a mitad, el Edge puede reintentar con `Range: bytes=X-` para resume parcial sin afectar el sync version.
- **Métricas separadas.** Core puede medir "cuántas IEAs consultaron sync" vs "cuántas IEAs efectivamente descargaron" como métricas distintas.

### 7.4 Resume parcial

**Recomendado, no obligatorio.** Si Core soporta `Range` headers para descargas parciales, el Edge puede reintentar descargas interrumpidas sin volver a empezar. Para conectividad IEA inestable, esto es relevante. Si no se implementa en la primera versión, el Edge reintentará desde cero cuando una descarga falla.

---

## 8. Integridad y autenticidad de los paquetes

### 8.1 Verificación SHA-256

Al descargar el .tar.gz, el Edge verifica el hash SHA-256 contra el valor `package_sha256` recibido en el pull metadata. Si no coincide, el paquete se descarta y se reporta error.

**Esto protege contra:** corrupción en tránsito, descarga incompleta, error de disco.

**Esto NO protege contra:** un atacante que controle Core y firme el hash de un paquete malicioso. Para eso se requiere firma criptográfica asimétrica.

### 8.2 Firma criptográfica del paquete (no en esta versión)

**Deuda técnica documentada.** Para defensa contra Core comprometido, el flujo correcto sería:

1. El proyecto YVY mantiene una clave privada **offline** (no en Core).
2. Cada release se firma con esa clave privada antes de subirse a Core.
3. Cada Edge tiene la clave pública correspondiente embebida en el código.
4. Al descargar, además de verificar SHA-256, verificar la firma con la clave pública.

**Por qué no se implementa ahora:**

- Para el piloto con 3 IEAs supervisadas, el modelo de amenazas no incluye "Core comprometido".
- Implementar correctamente requiere proceso operativo serio (ceremonia de firma, gestión de claves, plan de rotación).
- Agrega complejidad al deploy que no aporta valor inmediato.

**Cuándo agregarlo:** cuando el sistema se expanda a más IEAs y/o cuando se reciba financiamiento que permita establecer procesos operativos formales.

### 8.3 Confianza actual

La confianza en el canal viene de:

1. **TLS** sobre HTTPS protege confidencialidad e integridad del transporte.
2. **HMAC** del request autentica que el Edge es legítimo (Core sabe que es la station X).
3. **SHA-256** del paquete verifica que lo que se descarga es exactamente lo que se anunció.
4. **Confianza humana en Core.** La instancia de Core la opera el mismo equipo del proyecto.

Esto es suficiente para el piloto. La firma criptográfica es upgrade obligatorio antes de expansión masiva.

---

## 9. Política de Core sobre publicación de updates

### 9.1 Mínima funcionalidad para piloto

Core debe permitir:

- Subir un paquete .tar.gz al storage del server.
- Asociar el paquete a una versión semver (`edge_version`).
- Registrar la `released_at` (timestamp de publicación).
- Indicar `min_edge_version` requerido (versión mínima desde la cual se puede aplicar este update directo).
- Generar y registrar el SHA-256 del paquete.
- Atomicidad: la operación de "publicar" debe incrementar `sync_version` Y dejar el paquete disponible para descarga **en la misma transacción**. No puede haber estado intermedio donde el `sync_version` ya incrementó pero el archivo no existe.

### 9.2 Política recomendada

Sugerencias operativas (no son requisito técnico del contrato):

- **Soft launch:** publicar primero a una IEA de prueba antes de hacer público a las demás. Esto requeriría un mecanismo de "publicar a subset de stations", lo cual es funcionalidad adicional en Core. Si no está, alternativa simple: notificar manualmente al operador de una IEA, que ejecute `yvy check-updates`, que vea el update y decida si descargar. Las demás IEAs no lo descargarán hasta que se les indique.
- **Rollback de publicación:** si se detecta un bug en un release ya publicado, Core debe poder "despublicar" o publicar inmediatamente un release posterior corregido. La distribución acumulativa ayuda aquí: si publico 0.9.4 inmediatamente después de detectar bug en 0.9.3, las IEAs que aún no descargaron salteán 0.9.3 y van directo a 0.9.4.
- **Comunicación humana paralela:** los updates publicados deben comunicarse por canal humano (mail, Slack del proyecto) además del canal técnico. El operador IEA debe saber qué está descargando.

---

## 10. Bootstrap (Edge primera consulta)

Cuando un Edge nuevo consulta por primera vez, `X-Last-Sync-Version: 0`. Core debe responder con la metadata actual de updates.

**Caso extremo:** un Edge fresh install con software 0.9.0 consulta cuando Core tiene 0.9.5 disponible. Response indica "hay update 0.9.5, descargá". El Edge fresh, si pasó por el wizard de onboarding correctamente, probablemente no necesita ese update inmediatamente (ya tiene el software del pendrive). Pero conviene que sepa que hay una versión más reciente disponible para informar al operador.

**Decisión:** Core no diferencia bootstrap vs consulta normal. Siempre responde con el estado actual. El Edge decide qué hacer con la información (descargar inmediato, esperar, etc.).

---

## 11. Logging y observabilidad recomendados en Core

Para facilitar diagnóstico y métricas operativas, Core debería loguear de forma estructurada:

| Evento | Campos clave |
|---|---|
| `pull.request.received` | `station_uuid`, `last_sync_version`, `edge_version`, `received_at` |
| `pull.response.no_changes` | `station_uuid`, `sync_version_returned` |
| `pull.response.update_available` | `station_uuid`, `update_version_offered` |
| `pull.auth.failed` | `station_uuid`, `reason` (key_invalid, signature_mismatch, etc.) |
| `update.published` | `version`, `released_at`, `sha256`, `size_bytes`, `min_edge_version`, `new_sync_version` |
| `update.downloaded` | `station_uuid`, `version`, `bytes_transferred`, `duration_ms` |
| `update.download.failed` | `station_uuid`, `version`, `error_type` |

Esto permite construir dashboards de:

- Cuántas IEAs consultaron sync en las últimas 24h.
- Cuántas IEAs efectivamente descargaron cada release.
- Cuáles están atrasadas en versión.
- Tasa de fallos de descarga (puede indicar problemas de conectividad).

---

## 12. Resumen ejecutivo de lo que Core debe implementar

Para que el Edge pueda usar este canal, Core necesita implementar (en este orden de prioridad):

**Bloque 1: Endpoint de pull (bloqueante para Edge)**

1. `GET /api/v1/edge/sync` con autenticación HMAC, retornando JSON estructurado según sección 4.
2. Tabla o secuencia para `sync_version` global atómico.
3. Header `X-Server-Sync-Version` en todas las respuestas de los endpoints de ingest existentes (modificación de los handlers actuales).

**Bloque 2: Publicación de updates (bloqueante para tener algo que servir)**

4. Mecanismo para registrar un paquete (CLI tipo `yvy-server publish-update --file 0.9.3.tar.gz --min-edge-version 0.9.0 --notes "..."`).
5. Cálculo automático del SHA-256 al publicar.
6. Incremento atómico de `sync_version` al publicar.

**Bloque 3: Endpoint de descarga (bloqueante para Edge si quiere descargar)**

7. `GET /api/v1/edge/updates/<filename>` con autenticación HMAC, streaming del binario.
8. Headers de respuesta apropiados (`Content-Length`, `X-Package-SHA256`).
9. (Opcional, recomendado) soporte de `Range` headers para descargas parciales.

**Bloque 4: Logging y métricas (operativo, no bloqueante para funcionar)**

10. Logging estructurado de eventos según sección 11.
11. (Opcional) dashboard de Core que muestre estado de cada IEA: versión actual, último sync, etc.

---

## 13. Lo que Edge implementa en paralelo

Para contexto del equipo de Core, esto es lo que el Edge implementará simultáneamente (documentación separada para el equipo de Edge):

- `UpdateCheckerDaemon` (thread separado del sync push agent).
- Persistencia de `last_sync_version` en `app_config`.
- Persistencia de metadata de update pendiente en `app_config`.
- Modificación del HttpClient para extraer header `X-Server-Sync-Version` de respuestas de ingest.
- Trigger interno (`threading.Event`) entre sync agent y update checker.
- Sub-sección de UI en `SyncStatusView` mostrando estado de updates.
- Comando CLI `yvy check-updates` para trigger manual.

**Lo que Edge NO implementa en esta fase:**

- Descarga automática del paquete (la decisión de descargar es manual del operador).
- Instalación del paquete (Fase 12+).
- Verificación de firma criptográfica (deuda técnica documentada).

---

## 14. Versionado de este contrato

Este es contrato `v1.0` del canal Core → Edge. Cambios futuros que rompan compatibilidad incrementan el major (`v2.0`). Cambios que solo agregan claves al response sin remover nada existente son compatibles hacia atrás y no requieren nueva versión.

Todos los Edges que respeten el principio "ignorar claves desconocidas en el response" serán compatibles con versiones futuras sin necesidad de actualización.

---

**Fin del documento.** Para preguntas o ajustes al contrato antes de implementar, contactar a Gonzalo.
