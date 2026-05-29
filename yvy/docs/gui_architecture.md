# YVY — Arquitectura GUI

> Última actualización: 2026-05-28  
> Rama: `testing-iea7-deploy-v1`  
> Target hardware: netbook IEA (1366×768 típico, mínimo 1024×600)

---

## 1. Layout general

```
┌────────────────────────────── 1366px ──────────────────────────────────┐
│  HEADER 60px — PRIMARY #1E3A5F                                         │
│  [YVY logo 200px] [IEA Nº10 Posadas · CUE:540178700]                   │
│  [📡 sensor] [↻ sync] [🕐 NTP] [🛜 red] [🔔 bell] [● avatar]           │
├──────────┬─────────────────────────────────────────────────────────────┤
│ SIDEBAR  │                                                              │
│ 200px    │        ÁREA DE CONTENIDO                                     │
│ #E8E2D2  │        1166×708px (1366 - 200px sidebar)                     │
│          │        (view cacheada por key; se instancia una sola vez)    │
│ ⌂ Inicio │                                                              │
│ 📋 Form  │                                                              │
│ 📊 Dash  │                                                              │
│ ↻ Sync   │                                                              │
│ ? Ayuda  │                                                              │
│ ──admin──│                                                              │
│ 👥 Users │                                                              │
│ 📜 Logs  │                                                              │
│ 💾 Datos │                                                              │
│ ⚙ Config │                                                              │
└──────────┴─────────────────────────────────────────────────────────────┘
```

**Dimensiones clave** (definidas en `theme.py`):

| Constante | Valor |
|---|---|
| `WINDOW_DEFAULT_WIDTH` | 1280px |
| `WINDOW_DEFAULT_HEIGHT` | 768px |
| `WINDOW_MIN_WIDTH` | 1024px |
| `WINDOW_MIN_HEIGHT` | 600px |
| `HEADER_HEIGHT` | 60px |
| `SIDEBAR_WIDTH_EXPANDED` | 200px |
| `SIDEBAR_WIDTH_COLLAPSED` | 60px |
| `SIDEBAR_ITEM_HEIGHT` | 48px |

---

## 2. Mapa de vistas

| Sidebar key | View instanciada | Condición de render | Fuente de datos |
|---|---|---|---|
| `inicio` | `DashboardAdminView` | siempre | ⚠️ **Estático** (ver §7) |
| `formulario` | `EmpiricalListView` | `empirical_controller` + user real | ✅ Live DB |
| `dashboard` | `DashboardAdminView` | siempre | ⚠️ **Estático** |
| `sync` | `SyncStatusView` | `sync_controller` inyectado | ✅ Live DB |
| `ayuda` | `HelpView` | `help_repository` presente | 📁 Archivos MD en `resources/help/` |
| `usuarios` | `UsersView` | `users_admin_controller` + rol admin | ✅ Live DB |
| `logs` | `LogsView` | `list_audit_logs_uc` + rol admin | ✅ Live DB |
| `datos` | `DataView` | `export_*_uc + db_factory` + rol admin | ✅ Live DB |
| `config` | `SettingsView` | `update_retention_uc` + rol admin | ✅ Live DB |

Vista por defecto al login:
- alumno → `formulario`
- admin / superadmin / profesor → `dashboard`

---

## 3. Header — indicadores de estado (en vivo)

Los 4 chips del header se actualizan automáticamente cada **15 segundos** via `root.after()`.
El ciclo arranca en `show_main()` y se cancela en `show_login()` (cambio de usuario).

### Lógica por indicador

#### 📡 Sensor
Fuente: `sensor_status_fn: Callable[[], tuple[str, str]]` inyectado desde `launch_app.py`.

| Estado devuelto | Condición |
|---|---|
| `"ok"` `Sensor: hilo activo · WH1081 detectado` | `_collector.is_alive() == True` |
| `"warning"` `Sensor: pywws no disponible o USB sin driver` | collector es `None` (pywws no instalado o USB sin driver Zadig) |
| `"error"` `Sensor: hilo detenido (verificar USB)` | collector creado pero hilo muerto |

#### ↻ Sync
Fuente: `sync_controller.get_dashboard_data(recent_limit=0)` (sin cargar eventos).

| Estado | Condición |
|---|---|
| `"error"` | agent latched (AUTH_ERROR / CLOCK_ERROR) |
| `"error"` | `error_count > 0` |
| `"warning"` | `pending_count > 0` |
| `"neutral"` | `agent_state is None` (modo dev sin credentials) |
| `"ok"` | todo lo demás |

#### 🕐 NTP
Fuente: `agent_state.clock_offset_seconds` del sync agent.

| Estado | Condición |
|---|---|
| `"ok"` | `abs(offset) < 5s` |
| `"warning"` | `5s ≤ abs(offset) < 60s` |
| `"error"` | `abs(offset) ≥ 60s` |
| `"neutral"` | sin agent |

#### 🛜 Conectividad
Fuente: `agent_state.state` del sync agent.

| Estado | Condición |
|---|---|
| `"ok"` | `HEALTHY` |
| `"warning"` | `DEGRADED` o `DISCONNECTED` |
| `"neutral"` | `PAUSED` o sin agent |
| `"error"` | estados latched |

### Archivos relevantes

- `src/yvy/presentation/app.py` — `_update_header_status()`, `_poll_header()`, `_start_header_polling()`, funciones módulo `_derive_*`
- `src/yvy/presentation/components/header.py` — métodos `set_sensor_status()`, `set_sync_status()`, `set_ntp_status()`, `set_connectivity_status()`
- `src/yvy/presentation/components/status_indicator.py` — `StatusIndicator`, estados: `"ok"` / `"warning"` / `"error"` / `"neutral"`
- `scripts/launch_app.py` — `_sensor_status_fn` closure con `_collector.is_alive()`

---

## 4. Handlers — real vs estático vs stub

### Completamente funcionales ✅

| Acción | Handler | Destino |
|---|---|---|
| Login | `_handle_login` → `auth_controller.login()` | DB real |
| Avatar click | `UserMenuModal` | cambiar usuario |
| Formulario → Nueva obs | `EmpiricalWizardView` multi-step | DB real |
| Formulario → Ver detalle | `EmpiricalDetailModal` | DB real |
| Sync → Refrescar | `SyncStatusView.refresh()` | DB real |
| Sync → Sincronizar ahora | `force_wakeup_agent()` | sync agent |
| Sync → Recuperar buffer | `CatchupModal` con progreso | DB real + pywws |
| Sync → Pausar/Reanudar | `pause_agent()` / `resume_agent()` | sync agent |
| Config → Guardar retención | `UpdateRetentionPolicyUseCase` | DB real |
| Config → Forzar retention | `RunRetentionJobUseCase` en thread | DB real |
| Usuarios → CRUD | `UsersView` + `UserFormModal` | DB real |
| Logs → Filtros + tabla | `LogsView` | DB real |
| Datos → Exportar CSV | `DataView` → archivos CSV | DB real |
| Header indicators | polling 15s vía `root.after()` | DB + daemon |

### Solo stub / decorativo ⚠️

| Acción | Estado | Nota |
|---|---|---|
| 🔔 Bell notificaciones | `logger.info()` solamente | Sin UI visible |
| Dashboard → Exportar | Sin `command=` | Botón decorativo |
| Dashboard → Filtro período | Sin binding | Selector estático |
| Dashboard → "Ver todos →" | Sin binding | Decorativo |

### Datos 100% hardcoded (Dashboard) ⚠️

Todos los KPIs del `DashboardAdminView` son estáticos: `21.4 °C`, `68%`, `1013 hPa`, `12.3 mm`.
Los eventos mostrados tienen fechas de abril 2026 inventadas. **Ver §7.**

---

## 5. Tipografía

Fuente: **DejaVu Sans** (incluida en Python 3.12 via Tk). Monoespaciada: DejaVu Sans Mono.

| Constante | Tamaño | Peso | Uso principal |
|---|---|---|---|
| `FONT_DISPLAY` | 32px | bold | Título en login card |
| `FONT_H1` | 24px | bold | Títulos de view ("Dashboard", "Sincronización") |
| `FONT_H2` | 18px | bold | Definido, sin uso directo actual |
| `FONT_H3` | 14px | bold | Títulos de card interior |
| `FONT_BODY` | 11px | normal | Texto general, inputs, tabla |
| `FONT_BODY_BOLD` | 11px | bold | Labels de KPI, valores en tabla |
| `FONT_SMALL` | 10px | normal | Subtítulos, timestamps, tooltips |
| `FONT_TINY` | 9px | normal | Deltas de KPI, texto muy secundario |
| `FONT_KPI_VALUE` | 28px | bold | Número grande en KPI cards |
| `FONT_BUTTON` | 11px | bold | Todos los botones |
| `FONT_MONO` | 11px | mono | Logs, JSON |

**Nota para pantallas pequeñas**: `FONT_KPI_VALUE` (28px) puede ser grande a 1024×600.
El `rowheight=36` de la treeview de Sync con 10 filas = 360px solo de tabla.

---

## 6. Paleta de colores

| Constante | Hex | Uso |
|---|---|---|
| `PRIMARY` | `#1E3A5F` | Header, botones primarios, selección treeview |
| `PRIMARY_LIGHT` | `#3B5F82` | Hover botón primario |
| `ACCENT_OLIVE` | `#9AA223` | Borde activo sidebar, progresbar catchup |
| `ACCENT_GOLD` | `#C9A227` | Warnings, dorado |
| `SUCCESS` | `#7A9E1F` | Estados OK, oliva luz |
| `WARNING` | `#C9A227` | Estados warning, pending |
| `DANGER` | `#C2362A` | Errores, botón Danger |
| `BG_CREAM` | `#F5F1E8` | Fondo general de la app |
| `BG_CARD` | `#FFFFFF` | Cards, modals, inputs |
| `BG_SIDEBAR` | `#E8E2D2` | Fondo sidebar |
| `BG_HOVER` | `#DCD4C0` | Hover sidebar, trough progressbar |
| `BORDER` | `#D1C9B8` | Bordes de inputs y cards |
| `TEXT_PRIMARY` | `#2B2621` | Texto general |
| `TEXT_SECONDARY` | `#6B7280` | Subtítulos, metadata |
| `TEXT_ON_DARK` | `#FFFFFF` | Texto sobre header/primario |

---

## 7. Issues conocidos y TODO

### Crítico para credibilidad

**Dashboard con datos hardcoded** (`dashboard_admin.py`): todos los KPIs
(21.4 °C, 68%, 1013 hPa, 12.3 mm) y los 3 eventos son inventados con fechas
de abril 2026. Los alumnos los verán siempre igual.

- Fase futura: conectar a use cases de query real de `sensor_raw` + `empirical_record`.
- Mientras tanto: los datos son explícitamente un placeholder (visible en el docstring).

### Pestaña Inicio — TODO fase posterior

**Estado actual**: `inicio` redirige a `DashboardAdminView` (misma vista que `dashboard`).

**Intención final**: pantalla de "novedades + contenido educativo" con:
- Informes enviados desde el servidor central (`yvy-server`)
- Curiosidades meteorológicas
- Alertas de eventos climáticos notables
- Contenido motivacional para alumnos

Implementar cuando exista el módulo de push de contenido en `yvy-server`.
El código en `app.py::_build_view` tiene el TODO documentado.

### Indicadores del header — limitación conocida

El indicador de **sensor** muestra `"ok"` si el hilo daemon está vivo,
pero el hilo puede estar vivo y aun así fallar en cada lectura (WH1081
no conectado). En ese caso el log de `sensor.capture.failure` crece pero
el indicador dice "ok". Para mayor fidelidad habría que exponer el conteo
de fallos consecutivos del `SensorCollectorDaemon`.

### Indicadores del header — sin polling en pantalla de login

Los indicadores solo se actualizan cuando hay sesión activa (`show_main()`).
En el login screen el header no existe, así que no aplica.

---

## 8. Recomendaciones por tamaño de pantalla

### 1366×768 — netbook IEA típica ✅

Sin cambios necesarios. Layout diseñado para este target.

### 1280×768 — window default ✅

Content: 1080×708px — cómodo.

### 1024×600 — mínimo permitido ⚠️

| Problema | Recomendación |
|---|---|
| Sidebar consume 200px de ancho | Colapsar por defecto (60px) → content 964px |
| Treeview Sync: 10 filas × 36px = 360px | Reducir a 7 filas (saves 108px) |
| KPI card sync: width 240px puede apretar | Reducir a 200px |
| Padding general `SPACE_XL=24` | Reducir a `SPACE_MD=12` en vistas compactas |

### 800×600 — proyector / pantalla vieja

Actualmente fuera del mínimo (`WINDOW_MIN_WIDTH=1024`). Si se necesita:
- Sidebar colapsado obligatorio
- Dashboard: KPIs apilados verticalmente debajo del gráfico (en lugar de al lado)
- Sync: KPI card debajo del status card

---

## 9. Estructura de archivos de presentación

```
src/yvy/presentation/
├── app.py                          # MainApplication (orquestador Tk)
├── theme.py                        # Paleta, tipografía, spacing, ttk.Style
├── components/
│   ├── __init__.py
│   ├── header.py                   # Header 60px (4 indicadores + avatar)
│   ├── sidebar.py                  # Sidebar colapsable (SidebarItem)
│   ├── status_indicator.py         # Chip ok/warning/error/neutral
│   ├── catchup_modal.py            # Modal Recuperar buffer histórico
│   ├── modal.py                    # Base modal reutilizable
│   ├── data_detail_modal.py        # Modal detalle de dato
│   ├── user_form_modal.py          # Modal crear/editar usuario
│   ├── help_button.py              # Botón ? contextual
│   ├── help_modal.py               # Modal de ayuda
│   └── metric_carousel.py          # Carrusel de métricas (no usado aún)
├── views/
│   ├── login_view.py               # Pantalla de login
│   ├── dashboard_admin.py          # Dashboard (datos ESTÁTICOS — ver §7)
│   ├── sync_status_view.py         # Pantalla Sync (datos LIVE)
│   ├── help_view.py                # Pantalla Ayuda (archivos MD)
│   ├── onboarding/
│   │   └── wizard_view.py          # Wizard primera vez
│   ├── admin/
│   │   ├── users_view.py           # Gestión de usuarios
│   │   ├── logs_view.py            # Audit logs
│   │   ├── data_view.py            # Exportar CSV
│   │   └── settings_view.py        # Configuración retención
│   └── empirical/
│       ├── list_view.py            # Lista de observaciones
│       ├── wizard_view.py          # Wizard carga empírica
│       └── detail_modal.py         # Detalle observación
└── controllers/
    ├── auth_controller.py
    ├── empirical_controller.py
    ├── sync_controller.py          # SyncController + SyncDashboardData
    └── users_admin_controller.py
```
