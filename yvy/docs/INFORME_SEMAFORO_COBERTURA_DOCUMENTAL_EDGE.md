# Informe Semáforo — Cobertura Documental YVY Edge

> Diagnóstico de cobertura documental para la entrega de Práctica Profesionalizante III (Proyecto YVY).
> Compara la documentación mínima obligatoria de la consigna contra lo que **realmente** existe en el repo,
> verificando cada ítem contra el código, no contra lo que otro documento afirma.
>
> **Fecha del diagnóstico:** 2026-09-09
> **Repositorio evaluado:** `I:\.YVY_IEAProject\Fase_0\yvy` — rama `stab/ini-1-higiene` — `__version__ = 1.6.0`

**Leyenda:**

- 🟢 Existe, está actualizado y verificado contra el código
- 🟡 Existe pero está incompleto, desactualizado, o no pudo verificarse contra el código
- 🔴 No existe

**Alcance de la verificación:** se leyeron los 14 documentos de `docs/architecture/`, los `.md` operativos de `docs/`,
`docs/dnda/`, `docs/reporte_IEA/`, `README.md`, `CHANGELOG.md`, las 8 migraciones SQLite, `config/paths.py`,
`config/constants.py`, `src/yvy/__init__.py`, `scripts/INSTALL_UPDATE.bat`, `scripts/INICIAR_YVY.bat`, y se contrastó
contra `src/yvy/` capa por capa (domain → application → infrastructure → presentation/CLI). Documentos históricos
periféricos (`AUDITORIA_ARQUITECTURA_2026-07`, `PEER_REVIEW_*`, `gui_refactors`, `PLAN_ADOPCION_MYPY`, `historico/*`,
prompts) no se verificaron línea por línea; no cambian ningún veredicto.

---

## Tabla de evaluación

| Ítem | Estado | Evidencia (ruta:línea o archivo) | Comentario |
|---|---|---|---|
| **A. Documento de inicio** (qué es, objetivo, alcance, estado, dónde está cada cosa) | 🟡 | `README.md`; `docs/architecture/README.md`; `docs/architecture/01_arquitectura_general.md`; `docs/dnda/README_DNDA.md` | No existe **un** documento que cubra los cinco sub-puntos. `README.md` los intenta todos pero está gravemente desactualizado: dice "Fase 0 en curso (bootstrap del repo)", "Resumen al 26-Abr-2026", enfoque Poetry/Debian, y enlaza 6 archivos inexistentes (`YVY_Anexo_Tecnico_v3.md`, `YVY_Sistema_Local_v2.md`, `YVY_Plan_Fases.md`, `YVY_Progreso_v1.md`, `docs/handbook/` [vacío], `docs/diagrams/` [vacío]). `docs/architecture/README.md` + `01` son excelentes para "qué es / forma del sistema / qué tocar según qué cambió" y están verificados contra código, pero no cubren objetivo institucional ni estado. `dnda/README_DNDA.md` da "qué es + objetivo + flujo" correcto (menciona Python 3.12) pero está enmarcado para registro de obra y su snippet embebido dice `__version__ = "1.5.1"`. |
| **B. Arquitectura** (diagrama, componentes, relaciones, flujo de datos, infraestructura, comunicaciones) | 🟢 | `docs/architecture/01`–`13` + `README.md`; ~16 diagramas Mermaid embebidos; `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md:305-321` | El set de 13 documentos + índice es la parte más fuerte. Cubre las 5 capas, la regla de dependencia (DEP-1..4), el Composition Root, los 3 daemons, el modelo de threading, el flujo sensor→SQLite, el canal HMAC pull (envelope de 7 campos), la máquina de estados del agente, y OTA por slots. Se verificaron múltiples afirmaciones contra código (`bootstrap.py`, `envelope_builder.py`, `agent_state.py`, `config/paths.py`, migraciones): coinciden. La `CERTIFICACION` confirma que fue "verificada por máquina" con `archivo:línea`. Matiz menor: los diagramas son Mermaid inline, no los "12 SVG" que promete el README; `docs/diagrams/` está vacío (los SVG sueltos viven fuera del repo, en `i:\.docs_YVYEdge\...\Diagramas\`). |
| **C. Infraestructura Edge** (netbook, SO, dependencias, layout en disco) | 🟡 | `docs/MANUAL_INSTALACION_EDGE.md`; `docs/yvy_WINDOWS_24x7.md`; `docs/architecture/13_configuracion_deployment.md`; `docs/reporte_IEA/sensor_usb.md`; `requirements.prod.txt`; `src/yvy/config/paths.py` | SO real (Windows 10, `C:\YVY`) bien cubierto en MANUAL + `13` + `yvy_WINDOWS_24x7` (powercfg/registry detallados y verificables). Dependencias: `requirements.prod.txt` + pywws/usb1/WinUSB en `sensor_usb.md`. Layout en disco: `13` §2 + `YVY_Diseno_Instalacion_Updates.md` §3.1, coinciden con `INSTALL_UPDATE.bat` y `paths.py`. **Contradicción:** `README.md` sección "producción (netbook IEA)" describe **Debian 12 Bookworm + systemd + chrony + `sudo bash deploy/install.sh`** — un sistema Linux que no existe (`deploy/` no existe, todo el deploy real es `.bat` sobre Windows). Hay que juntar 4 docs para tener el cuadro completo. |
| **D. Software y componentes** por módulo (domain, application, infrastructure, presentation/CLI, sync agent, OTA updater) | 🟡 | `docs/architecture/03`–`10`; `docs/yvy_CLI_GUIA.md`; `DIAGNOSTICO_ARQUITECTONICO.md` (raíz) | Función, ubicación real y tecnologías de cada capa están en `03` (domain), `04` (application), `05` (infrastructure), `06` (presentation/CLI), `09` (sync agent), `10` (OTA) — nombran archivos reales, verificados. Sync agent y OTA especialmente sólidos y coinciden con `sync_agent.py` / `agent_state.py` (migración v13) y `installer.py` / `INSTALL_UPDATE.bat` (certificado en campo, `ACTA_CERTIFICACION_OTA_1.5.x.md`). **Falta:** el desglose sistemático "entradas/salidas + cómo se ejecuta + cómo se verifica" por módulo que pide la consigna está disperso (verificación por CLI en `yvy_CLI_GUIA`, testing en `12`), no tabulado. Y `DIAGNOSTICO_ARQUITECTONICO.md` en la raíz (2026-05-26) es un mapa de componentes **radicalmente obsoleto** que afirma que el sync agent, OTA y catchup "no existen / están rotos" (ver discrepancia #3). |
| **E. Datos** (origen WH1081/pywws, formato, frecuencia, esquema SQLite real, diccionario de datos, unidades, transformaciones) | 🟡 | `migrations/001_initial_v8.sql`–`008_updates_v15.sql`; `docs/architecture/08_adquisicion_y_persistencia.md:82-207`; `src/yvy/config/constants.py:20,54` | Esquema: las 8 migraciones (v8→v15) están bien comentadas y el ER de `08` §3 coincide con ellas (tablas `empirical_observation`/`empirical_event` v11, `sync_agent_state` singleton v13; `empirical_data`/`comments` reconocidas como legacy). Diccionario de datos: sólo embebido en comentarios SQL (`migrations/001` lista claves de `app_config` y `app_metrics`) + rangos `CHECK`; **no hay un diccionario con unidades y significados**. Frecuencia inconsistente entre docs: `08` dice "~48 s", `constants.py:54` dice `SENSOR_LIVE_INTERVAL_SECONDS = 60`, `YVY_Diseno` dice "la estación persiste cada 5 min", `validacion_ota_e2e` dice "SyncAgent cicla cada ~10 s". `constants.py:20 SCHEMA_VERSION_LOCAL = 8` **miente** (esquema real v15, trackeado por tabla `schema_version`; lo admite `CERTIFICACION` F-5). `wind_direction`: la migración pone `CHECK BETWEEN 0 AND 360` pero `CHANGELOG` [1.4.0] dice que la DB guarda escala **1–16** — sin nota que lo reconcilie. Transformaciones (event_id uuid5 determinístico, canonicalización de timestamp, `is_valid`) sí están documentadas en `migrations/001` + `08`. |
| **F. Instalación y configuración** (procedimiento reproducible: requisitos, hw, sw, versiones, comandos, resultado esperado, verificación) — INSTALL_UPDATE.bat, pendrive, flat→slot | 🟡 | `docs/YVY_Diseno_Instalacion_Updates.md`; `docs/validacion_ota_e2e.md` (13 pasos); `docs/MANUAL_INSTALACION_EDGE.md`; `scripts/INSTALL_UPDATE.bat` (comentado); `docs/OTA_FIXES_1.5.1.md` | `INSTALL_UPDATE.bat` y **flat→slot**: muy bien documentados (`YVY_Diseno` §3–§7, `10`, comentarios del `.bat` paso 0 `:migrate_flat_to_slots`, `validacion_ota_e2e` con comandos exactos y salida esperada) y **certificado en campo** (`ACTA_CERTIFICACION_OTA_1.5.x.md`). Pendrive (uso): `MANUAL_INSTALACION_EDGE` (6 pasos operativos con pantallas esperadas), `versionado.md` "Primera instalación (USB)". **Huecos:** (1) no hay procedimiento reproducible para **construir** el pendrive — `scripts/preparar_usb.py` existe pero ningún doc explica cómo correrlo; (2) etiquetas de versión obsoletas: `MANUAL` dice "para YVY Edge 1.5.x, 29/06/2026", `validacion_ota_e2e` está escrito para 1.4.0→1.5.0 y usa claves `app_config` pre-refactor (`update_pending.version_available`, `update.install_status`) que ya no existen así (hoy es la clave JSON única `update_pending` + `update_install.status`); (3) el `station_credentials.json` de `validacion_ota_e2e`/`configure_sync_GUIA` muestra campos `key`/`server_url` cuando el real es `station_uuid`/`key_version`/`key_hmac_hex` con la URL en `app_config.sync_server_url`. |
| **G. Operación** (iniciar/detener/reiniciar, verificar estado, logs, backup, recuperación) | 🟢 | `docs/yvy_CLI_GUIA.md`; `docs/architecture/07_runtime_bootstrap_ciclo_de_vida.md:766-795`; `docs/architecture/12_calidad_testing_observabilidad.md:826-838`; `docs/architecture/13_configuracion_deployment.md:966-977`; `docs/yvy_WINDOWS_24x7.md`; `scripts/INICIAR_YVY.bat` | Iniciar: `INICIAR_YVY.bat` + autoarranque (`yvy_WINDOWS_24x7` M4). Detener/reiniciar: `07` §5 ("la X no cierra; se mata por proceso") + `yvy_CLI_GUIA` "Limitaciones" ("el sync agent sólo se reinicia matando el launcher"). Verificar estado: `yvy_CLI_GUIA` es completo (`status`, `info`, `test sensor/db/sync` con salidas de ejemplo e interpretación). Logs: `12` §5 (`STABLE_ROOT/data/logs`, `RotatingFileHandler`) + `MANUAL` (`C:\YVY\data\logs\yvy_app.log`). Backup: `INICIAR_YVY.bat` hace backup diario de la DB con retención 30 días (verificado en el `.bat`); esto sólo está descrito en `docs/fixes_pre_piloto.md` FIX 4 (doc histórico), no en una referencia operativa. Recuperación: `hero-rescue` (`06`, `11`, `13`), `rollback` (`yvy_CLI_GUIA`), restaurar backup + borrar `-wal`/`-shm` (`fixes_pre_piloto`). Todo verificado contra los `.bat` y handlers del CLI. |
| **H. Problemas conocidos** — ¿registro Problema→Síntoma→Causa→Diagnóstico→Solución? Bonpland 11-Ago-2026? bug doble-serialización Garupá? | 🟡 | `docs/OTA_FIXES_1.5.1.md`; `docs/reporte_IEA/{sensor_usb,catchup_vs_live,dashboard_performance}.md`; `CHANGELOG.md` [1.5.1]; `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md:366-476` (F-1..F-7); `docs/MANUAL_INSTALACION_EDGE.md` "Problemas frecuentes" | **No existe un registro consolidado** ni una plantilla Problema→Síntoma→Causa→Diagnóstico→Solución. Hay material con esa forma **disperso** en ≥6 documentos: `OTA_FIXES_1.5.1` (Síntoma/Causa raíz/Fix), `reporte_IEA/*` (Síntoma/Causa/Estado), `CERTIFICACION` §3 (Evidencia/Impacto/Riesgo/Causa/Mitigación — lo más cercano al formato pedido, pero para hallazgos arquitectónicos, no incidentes de campo), `CHANGELOG` (narrativas de fix), `MANUAL` (tabla de troubleshooting operativo). **Incidente Bonpland 11-Ago-2026: NO existe** en ningún archivo del repo ni de `i:\.docs_YVYEdge\` ni de `FasesRaR\` (búsqueda de "bonpland" / "2026-08-11" / "agosto": cero resultados de incidente). **Bug de doble-serialización de Garupá:** el bug de payload doble-codificado **sí está documentado** como fix de código (`CHANGELOG` [1.5.1] con causa+fix+test de regresión `test_sync_payload_roundtrip.py`, `ACTA_CERTIFICACION_OTA`, `yvy_CLI_GUIA` comando `queue purge-stale-empirical`) — pero **nunca ligado a "Garupá"** (que sólo aparece como nombre de IEA de ejemplo en salidas de CLI) ni en formato de incidente. Además, `catchup_vs_live.md` describe el conflicto USB live/catchup como "Limitación conocida" con "fixes pendientes" cuando `sesion_2026-06-01.md` + `CHANGELOG` dicen que la coordinación `request_pause()/signal_resume()` ya se implementó. |
| **I. Decisiones técnicas** | 🟢 | Sección "Decisiones arquitectónicas actuales" en cada `docs/architecture/01`–`13`; `docs/observatorio_decisiones.md` (D78–D82, con fecha); `docs/YVY_Diseno_Instalacion_Updates.md:686-701` (§13 registro); `docs/POLITICA_VERSIONADO.md`; `docs/PLAN_MAESTRO_ESTABILIZACION.md:30-90` | Bien cubierto. Cada doc de arquitectura tiene su tabla "Decisión / Estado / Por qué". `observatorio_decisiones.md` es un registro tipo-ADR fechado (se verificó D78: los umbrales de probable helada del doc coinciden con `domain/observatorio/frost_detection.py`; D80: bandas 18–08 hardcoded coinciden con `night_periods.py`). `YVY_Diseno_Instalacion_Updates` §13 lista las decisiones del OTA con su fuente. `PLAN_MAESTRO_ESTABILIZACION` §2/§9 documenta las 4 causas raíz y las 5 recomendaciones descartadas. Salvedad: están distribuidas, no hay un log ADR único. |
| **J. Estado actual** — ¿documento único IMPLEMENTADO / EN DESARROLLO / PENDIENTE / PROPUESTO? | 🔴 | `DIAGNOSTICO_ARQUITECTONICO.md` (raíz, 2026-05-26); `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md`; `docs/PLAN_MAESTRO_ESTABILIZACION.md`; `README.md` "Estado del proyecto" | **No existe** un documento único con esas cuatro categorías. El que estructuralmente se le parece — `DIAGNOSTICO_ARQUITECTONICO.md` con columnas IMPLEMENTADO/STUB/muerto/roto — está en la **raíz del repo** y es de 2026-05-26: contradice frontalmente al estado real (afirma que sync agent, OTA y catchup no existen). El documento de estado real y verificado es `CERTIFICACION_ARQUITECTONICA_2026-07.md` (1.6.0, 2026-07-11, notas por área, "readiness APTO", deuda F-1..F-7 priorizada) pero **no** hace la distinción IMPLEMENTADO/EN DESARROLLO/PENDIENTE/PROPUESTO y convive con el diagnóstico obsoleto. `README.md` "Estado del proyecto" dice "Fase 0 en curso". Los docs de arquitectura excluyen roadmap por diseño. |
| **K. Trazabilidad** — ¿docs con fecha de última actualización + versión de código correspondiente? | 🔴 | `docs/architecture/01`–`13` (sin fecha ni versión); `docs/CERTIFICACION_ARQUITECTONICA_2026-07.md:653-655`; `docs/POLITICA_VERSIONADO.md:2`; `docs/observatorio_decisiones.md`; `docs/MANUAL_INSTALACION_EDGE.md:318` | Práctica **inconsistente**. Los 13 documentos de arquitectura — la fuente de verdad — **no llevan ni fecha ni "corresponde a v1.6.0"**; sólo dicen "ante discrepancia, el código gana", sin dar al lector un ancla temporal. Sí llevan fecha+versión: `CERTIFICACION` ("@ 1.6.0, 2026-07-11, verificado contra el árbol de trabajo", el estándar de oro), `POLITICA_VERSIONADO` ("1.0 · 2026-06-20"), `observatorio_decisiones` (fecha por decisión), `fixes_pre_piloto` ("2026-05-31, commit e594ec9"), los audits `*_2026-07`. Llevan fecha pero con versión ya obsoleta: `MANUAL` ("1.5.x, 29/06/2026"). Sin nada: `yvy_CLI_GUIA`, `yvy_WINDOWS_24x7`, `configure_sync_GUIA`, `gui_architecture`, y `versionado.md` (dice "valor actual 1.4.0"). |

---

## Discrepancias código ↔ documentación

1. **`README.md` — sección "producción (netbook IEA)" describe un sistema Linux inexistente.** Dice Debian 12 Bookworm, systemd, chrony, `grupo plugdev`, `sudo bash deploy/install.sh`. El deploy real es Windows 10 / `C:\YVY` / scripts `.bat`; `deploy/` no existe en el repo.

2. **`README.md` enlaza 6 documentos/carpetas que no existen:** `YVY_Anexo_Tecnico_v3.md`, `YVY_Sistema_Local_v2.md`, `YVY_Plan_Fases.md`, `YVY_Progreso_v1.md`, `docs/handbook/` (sólo `.gitkeep`), `docs/diagrams/` (sólo `.gitkeep`), `deploy/README.md`.

3. **`DIAGNOSTICO_ARQUITECTONICO.md` (raíz) y su copia byte-idéntica `docs/dnda/arquitectura/docs_fuente/EDGE_diagnostico_arquitectonico.md`** (2026-05-26, 452 líneas cada una) afirman como hecho vigente: *"SyncAgentDaemon no existe"*, *"sync_queue crece sin límite, ningún dato llega al servidor"*, *"SyncController no wired"*, *"UpdateManager no existe / `infrastructure/updates/` es stub"*, *"Flujo 5 Sincronización CRÍTICO ROTO"*. Todo falso en 1.6.0: existen y están certificados en campo `infrastructure/sync/sync_agent.py`, `update_checker_daemon.py`, `infrastructure/updates/installer.py`+`retention.py`, `application/services/updates_service.py` (ver `ACTA_CERTIFICACION_OTA_1.5.x.md`, `CHANGELOG` hasta 1.6.0). Además la versión DNDA está citada como respaldo por `dnda/arquitectura/ARQUITECTURA_GENERAL.md`.

4. **`src/yvy/config/constants.py:20` — `SCHEMA_VERSION_LOCAL: Final[int] = 8`.** El esquema real es v15 (migraciones 001–008 hacen `INSERT ... schema_version VALUES (15)`). Constante muerta y engañosa (también señalada por `CERTIFICACION` F-5).

5. **Tabla `update_log` — documentada como bitácora OTA, no usada.** `docs/architecture/08_adquisicion_y_persistencia.md:145` y `10_ota_updates.md:525` dicen que instalaciones/rollbacks OTA se registran en `update_log`. En `src/` la tabla `update_log` **no se referencia nunca**; los eventos OTA (`UPDATE_REQUESTED/COMPLETED/FAILED/ROLLBACK_MANUAL/RELEASE_MARKED_STABLE`) se escriben en `audit_logs` (`infrastructure/updates/installer.py:226,315`, `retention.py:161,186`, `post_boot_check.py:131`; migración v15). `update_log` (v8) es para `file_type` help_content/help_image/app_config, concepto legacy sin uso.

6. **Zona horaria: `America/Argentina/Buenos_Aires` en el código vs `America/Argentina/Cordoba` en la doc.** `src/yvy/presentation/views/empirical/wizard_view.py:72` fija `_TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")`; `src/yvy/presentation/app.py:161`, `domain/sync/repository.py:101` y los docs (`02` §6, `06`, `MANUAL`) dicen `America/Argentina/Cordoba`. Ambas son UTC−3 (sin efecto en runtime hoy), pero es inconsistencia interna del código y contradicción con la doc; el propio `CHANGELOG_FASE9_WIRING.md` marca el hardcode como punto a cambiar.

7. **`wind_direction`: escala del esquema vs escala real.** `migrations/001` define `wind_direction REAL CHECK(... BETWEEN 0 AND 360)` (grados); `CHANGELOG` [1.4.0] indica que la DB almacena `wind_direction` en escala 1–16 y que la query de la rosa se corrigió a `(CAST(wind_direction AS INT) - 1) % 16`. Ningún diccionario de datos reconcilia grados vs 1–16.

8. **URL del servidor divergente entre docs.** `MANUAL_INSTALACION_EDGE.md` y `CHANGELOG` usan `https://edge.yvyedge.com`; `configure_sync_GUIA.md` (Opción B) y las salidas de ejemplo de `yvy_CLI_GUIA.md` / `Test sync` usan `https://yvy-edge.tecnicatura.edu.ar`. `configure_sync_GUIA.md` además afirma `key_version` "Actualmente sólo 1".

9. **`validacion_ota_e2e.md` usa claves `app_config` pre-refactor.** Documenta `update_pending.version_available`, `update_pending.package_url`, `update.current_release`, `update.install_status`. El código actual guarda el pending como **una sola clave JSON `update_pending`** (`infrastructure/persistence/app_config_repository.py:27,183`, con dual-write legacy de `update_pending.edge_version` etc.) y usa `update_install.status`. El campo `station_credentials.json` del doc (`key`, `server_url`) tampoco coincide con el real (`station_uuid`, `key_version`, `key_hmac_hex`; URL en `app_config.sync_server_url`).

10. **`gui_architecture.md` §4/§7 — "Dashboard con datos 100% hardcoded (21.4 °C, 68 %, 1013 hPa, eventos de abril 2026 inventados)".** El `dashboard_admin.py` actual consulta datos reales: `_query_kpis()` + `ComputeDerivedUseCase` + `QuerySensorAggregatedUseCase` (cableado desde v1.0.1/1.1.0; `dashboard_admin.py:189-259`). El doc quedó obsoleto. (La nota "Exportar decorativo — TODO" del docstring sí sigue vigente.)

11. **`catchup_vs_live.md` — conflicto USB presentado como abierto.** Lista `LIBUSB_ERROR_ACCESS` como "Limitación conocida" con "Opciones de fix (pendientes)". `sesion_2026-06-01.md` + `CHANGELOG` describen la coordinación pausa/resume ya implementada en `infrastructure/pywws/live_source.py` + `presentation/controllers/sync_controller.py`.

12. **`versionado.md` — congelado en 1.4.0.** Tabla de versiones "valor actual 1.4.0" en las cuatro fuentes; "Historial de deploys" termina en "Piloto IEA 7 — 2026-06-01 — 1.0.0". Código y `CHANGELOG` van por 1.6.0.

13. **Nombre del entry point.** `docs/architecture/13_configuracion_deployment.md:952` llama al arranque `INICIAR.bat`; el archivo real es `INICIAR_YVY.bat` (el doc `10` sí usa el nombre correcto).

14. **`README.md` / `pyproject.toml` — Python 3.11 vs 3.12.** README dice "Python 3.11+ (Debian 12 trae 3.11)"; `pyproject.toml:11` `python = "^3.11"`, pero `pyproject.toml:159` `python_version = "3.12"` y todo el runtime real (venvs, `python-3.12.10-amd64.exe`, `INSTALL_UPDATE.bat` busca `py -3.12`, docs de arquitectura) es 3.12.10.

15. **Comportamiento real no mencionado en la doc de arquitectura:** el backup diario de la DB (`scripts/INICIAR_YVY.bat`, retención 30 días, `forfiles /D -30`) sólo está documentado en `docs/fixes_pre_piloto.md` (histórico); los docs `13` (Deployment) y `12` (Observabilidad) no lo mencionan.

16. **Positivo (sin discrepancia):** las variables de entorno documentadas en `13` §3 (`YVY_ROOT`, `YVY_SYNC_URL`, `PYTHONIOENCODING`, `NO_COLOR`) son **exactamente** las que lee el código (`infrastructure/system/paths.py:37`, `cli/handlers/sync_config.py:77`, `cli/formatting.py:30,38`). No hay env vars documentadas que el código ignore.

17. **Discrepancia que el propio proyecto declara (no re-verificada en este diagnóstico):** `CERTIFICACION` F-1 dice que `scripts/launch_app.py:443` lee `station_credentials.json` con `encoding="utf-8"` mientras los otros 5 sitios usan `utf-8-sig` — con un BOM puede dejar mudo el sync agent en silencio.

---

## Top 5 gaps de mayor impacto en una Prueba de Transferencia real

*(alguien que sólo tiene la doc, sin poder preguntar)*

### 1. No hay documento de estado confiable, y el más visible miente

Quien abra la raíz del repo encuentra `DIAGNOSTICO_ARQUITECTONICO.md` ("Diagnóstico Arquitectónico Exhaustivo")
afirmando que la sincronización, el OTA y el catchup no existen o están rotos — lo contrario de la realidad, y
además copiado dentro del paquete DNDA. El evaluador o desconfía de toda la documentación, o repite afirmaciones
falsas. No hay un doc único IMPLEMENTADO/EN DESARROLLO/PENDIENTE/PROPUESTO que lo corrija.
*(Ítems J, D; discrepancias #3, #11.)*

### 2. El `README.md` — la puerta de entrada — describe otro proyecto

Apunta a Debian/systemd/Poetry/`deploy/install.sh`, dice "Fase 0 en curso" y enlaza 6 archivos inexistentes. El
único documento que todos abren primero es inservible para orientarse, y contradice al deploy real
(Windows/`C:\YVY`/`.bat`). *(Ítem A; discrepancias #1, #2, #14.)*

### 3. La documentación de arquitectura no tiene trazabilidad

Los 13 documentos de `docs/architecture/` son precisos, pero ninguno dice "actualizado a 1.6.0" ni lleva fecha. Un
evaluador no puede saber si `08_adquisicion_y_persistencia` refleja el código que tiene delante o una versión de
hace meses, y no tiene forma de fechar ninguna afirmación. Sin ese ancla, "el código gana ante discrepancia" no
ayuda a quien no puede correr el código. *(Ítem K.)*

### 4. No hay registro de problemas conocidos con estructura Problema→Síntoma→Causa→Diagnóstico→Solución

Los incidentes reales y recurrentes (driver USB del sensor, crash-loop por doble-serialización, pérdida de datos
post-OTA, lock USB live/catchup) están dispersos en `CHANGELOG`, `OTA_FIXES_1.5.1`, `reporte_IEA/*`, `CERTIFICACION`
§3 — y algunos están obsoletos (`catchup_vs_live`). Un evaluador que en campo tope con cualquiera de estos no tiene
un único lugar donde mirar, y los incidentes concretos que se le mencionarían (Bonpland, 11-Ago-2026) no están
documentados en ningún lado. *(Ítem H.)*

### 5. Diccionario de datos incompleto y contradictorio

El esquema está en las migraciones, pero no hay diccionario con unidades y significado, `SCHEMA_VERSION_LOCAL = 8`
contradice el v15 real, `wind_direction` se guarda en escala 1–16 pero el `CHECK` dice 0–360, y la frecuencia de
muestreo aparece como ~48 s / 60 s / 5 min según el doc. Quien reconstruya el análisis desde la base SQLite sola
interpretará mal la dirección del viento y la cadencia temporal. *(Ítem E; discrepancias #4, #7.)*

### Casi-gap (mención)

Los documentos de instalación cargan versiones obsoletas (`MANUAL` "1.5.x", `validacion_ota_e2e` "1.4→1.5" con
claves de config pre-refactor, `versionado.md` clavado en 1.4.0) y la URL del servidor difiere entre
`edge.yvyedge.com` y `yvy-edge.tecnicatura.edu.ar` — un evaluador siguiendo el procedimiento al pie de la letra
configuraría mal el sync. *(Ítem F; discrepancias #8, #9, #12.)*
