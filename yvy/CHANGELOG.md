# CHANGELOG

## [1.1.0] - 2026-06-03

### Added
- Sistema de ayuda contextual extendido ("Pizarra YvY"):
  - Tooltips de hover con resumen corto en widgets marcados (dwell 400ms).
  - Panel lateral izquierdo expandible (`PizarraYvY`) con contenido completo desde "Saber más".
  - Navegación a conceptos relacionados mediante chips clickeables con historial back.
  - Mutuamente excluyente con menú lateral (abre pizarra → colapsa menú; expande menú → cierra pizarra).
- Campos `summary`, `related` por artículo en `resources/help/index.json` (opcionales, con fallback).
- Campos `version` y `language` en raíz de `resources/help/index.json`.
- Frontmatter YAML en archivos `.md` para metadata (`language`).
- `HelpRepository.get_related(key)` y `HelpRepository.get_language()`.
- `MainApplication.open_pizarra(article_key)` — API pública para abrir la pizarra desde cualquier vista.
- Wiring de `HelpButton` en vista Dashboard:
  - KPIs: Temperatura exterior, Humedad exterior, Presión atmosférica, VPD actual.
  - Header dinámico del gráfico (key cambia según gráfico seleccionado).
  - Sección "Diagnóstico del día".
  - Sección "Observaciones empíricas recientes".

### Changed
- `HelpButton` se activa por hover con dwell-time de 400ms (además de click directo como fallback).
- `HelpButton` acepta parámetro `on_expand: Callable[[str], None] | None`.
- `HelpModal` muestra `summary` corto en lugar del `body_md` completo.
- `HelpModal` incluye botón "Saber más →" cuando el caller provee callback `on_expand`.
- `Sidebar` acepta parámetro `on_toggle: Callable[[], None] | None` para coordinación externa.
- `HelpArticle` agrega campos `language`, `summary`, `related`.

### Compatibility
- Sin breaking changes en la API pública.
- Vistas distintas a Dashboard mantienen comportamiento anterior de `HelpButton` (sin on_expand).
- Artículos `.md` sin frontmatter funcionan normalmente.
- Artículos sin `summary` o `related` en index.json funcionan con fallbacks.

## [1.0.1] - 2026-06-02

### Added
- Indicadores derivados en Dashboard: VPD, punto de rocío, tendencia de presión, amplitud térmica.
- 4 nuevos tipos de gráfico: VPD, Punto de rocío, Tendencia de presión, Amplitud térmica diaria.
- KPI "VPD actual" en sidebar del Dashboard con zona agroclimática y lluvia del día.
- Sección "Diagnóstico del día" generada automáticamente.
- `ComputeDerivedUseCase` para cálculo de indicadores derivados (sin acceso a DB propio).
- 5 nuevos artículos de ayuda en categoría "Indicadores derivados".

### Changed
- Dashboard por defecto carga gráfico VPD en lugar de temperatura.
- Sidebar inicia siempre colapsado.
- Botones de acciones en UsersView correctamente visibles (fix layout Tkinter).

### Fixed
- Dark mode: normalización de colores 12-dígito de Windows Tk (`#rrrrggggbbbb` → `#rrggbb`).
- Bidirectional theme toggle mediante widget tagging.
- Gráficos matplotlib siempre en modo claro (`_yvy_skip_recolor=True`).

## [1.0.0] - 2026-05-15

### Added
- Sistema de ayuda in-app (Fase 8): `HelpRepository`, `HelpModal`, `HelpButton`, `HelpView`.
- Exportación de datos CSV procesado y crudo.
- Administración de usuarios con roles (Alumno, Profesor, Admin, Superadmin).
- Sincronización offline-first con servidor central.
- Recupero de buffer del sensor WH1081.
- Política de retención configurable.
- Wizard de onboarding para primera configuración.
- Dashboard con KPIs y gráficos de sensor en tiempo real.
- Formulario de observaciones empíricas.
