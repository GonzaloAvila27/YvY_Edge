# Acta de certificación — Canal OTA YVY Edge 1.5.x

**Fecha de test en campo:** 2026-07 · **Resultado: ✅ CERTIFICADO** (con 1 hallazgo menor de UI, no bloqueante)

## Alcance del test

Nodo real (IEA), instalación manual de **1.5.1** (con los fixes del ciclo: HMAC canal
pull, pending obsoleto, empírico doble-codificado, auto-purga, aislamiento de datos
CODE_ROOT/STABLE_ROOT, `INSTALL_UPDATE.bat` CRLF/ASCII + `_install_hooks.py`), seguido
del ciclo OTA completo contra YVY Core.

## Resultados

| # | Verificación | Resultado |
|---|---|---|
| 1 | Salto OTA **1.5.1 → 1.5.3** (dummy) — flujo completo: check → download (SHA-256) → install → reboot | ✅ |
| 2 | Segundo salto **→ 1.5.4** (certifica repetibilidad de futuras actualizaciones) | ✅ |
| 3 | **Preservación de `data/`**: usuarios, credenciales y configuración intactos tras cada update (valida el fix de aislamiento de datos por slots) | ✅ |
| 4 | Instalación disparada desde la **campana/notificación** (UpdateModal) | ✅ |
| 5 | Botón **"Instalar"** de la vista *Enlace → Actualizaciones* | ⚠️ placeholder muerto → **removido** (ver hallazgo) |

## Hallazgo (no bloqueante): botón "Instalar" muerto por construcción

- **Ubicación:** `presentation/views/sync_status_view.py:617-622`.
- **Causa raíz (verificada en código):** el botón se crea con `state="disabled"`
  hardcodeado, **sin `command`** y **sin guardarse referencia** — por lo que
  `_refresh_updates_section()` (que sí actualiza "Verificar ahora" y "Descargar
  actualización") no puede habilitarlo jamás. Es un placeholder que quedó sin cablear.
- **Descartadas:** la carrera de escritura del pending (H10 — se auto-repara en el
  siguiente poll, no produce gris persistente), el gate de rol del `UpdateModal`
  (verificado: construye `role.value` correctamente) y el aislamiento de datos
  (corregido y validado en este mismo test).
- **Nota de proceso:** ni la auditoría ni el peer review lo detectaron — ambos
  diagnosticaron el gate del `UpdateModal` (otro botón, que funciona). Un widget sin
  referencia es invisible al análisis por grep; el test de campo lo encontró.
- **Workaround operativo vigente:** instalar desde la campana (path certificado ✅).
- **Resolución aplicada (2026-07): botón REMOVIDO** (`sync_status_view.py`), no cableado.
  Decisión de producto: la instalación por campana es el path certificado; un botón
  placeholder muerto es peor que su ausencia, y evitar un segundo punto de disparo del
  install reduce superficie. La vista mantiene el estado "descargado, listo para
  instalar" (informativo). Verificado: compila + ruff verde.
  - *Follow-up opcional (no urgente):* ajustar ese texto para orientar a la campana.

## Implicancias para el programa (PLAN_MAESTRO_ESTABILIZACION)

- **INI-0 / R0: CERRADA.** Se desbloquean INI-2 (utilidades sobre familia updates) e
  **INI-3 (consolidación Updates + Composition Root)** — la cadena crítica.
- El canal OTA queda como **herramienta de release confiable** para todo el roadmap:
  cada release futuro puede distribuirse por OTA con rollback automático.
- El hallazgo del botón se incorpora a **R1** (épica 1.1 o propia, tamaño S).

## Baseline certificado

| Componente | Versión |
|---|---|
| YVY Edge (nodo de test) | 1.5.4 (dummy sobre base 1.5.1) |
| Instalador / slots | `__installer_version__` 1.4.1, `INSTALL_UPDATE.bat` CRLF/ASCII + hooks |
| YVY Core | master consolidado (fix 500 `/edge/updates` + Dockerfile Opción A) |
