# Fase 9 — Wiring: Formulario Empírico en la UI

## Qué se hizo

### Problema
Fase 8.5 implementó el backend completo del formulario empírico (dominio, use cases, repositorio, controller, views). Sin embargo, la pantalla "Formulario" del sidebar mostraba un placeholder (`_PlaceholderView`) porque `_build_view()` en `app.py` no tenía un caso para `key == "formulario"`. El mismo problema afectaba a `inicio` (pantalla de inicio para alumnos).

### Archivos modificados

#### `src/yvy/infrastructure/persistence/app_config_repository.py`
- Agregado `get_station_uuid() -> uuid.UUID`.  
- Hace que `AppConfigRepository` satisfaga el Protocol `AppConfigReader` (dominio) sin necesidad de un adaptador separado.  
- Lee el valor de la clave `"station_uuid"` en `app_config`. Lanza `RuntimeError` si no está configurado (indica onboarding incompleto).

#### `src/yvy/presentation/app.py`
- **Imports**: agregados `EmpiricalDetailModal`, `EmpiricalListView`, `EmpiricalWizardView` y `uuid`.
- **TYPE_CHECKING**: agregado `EmpiricalController`.
- **`MainApplication.__init__`**: nuevo parámetro `empirical_controller: EmpiricalController | None = None`. Se almacena en `self._empirical_controller`.
- **`_build_view("formulario")`**: cuando `empirical_controller` está inyectado y el usuario logueado es `User` (no mock), construye `EmpiricalListView` con los callbacks `on_open_wizard` → `_show_empirical_wizard` y `on_open_detail` → `_open_empirical_detail`.
- **`_show_empirical_wizard()`**: reemplaza el contenido visible con un `EmpiricalWizardView` fresco (no cacheado, para que cada nueva carga empiece limpia). Al completar llama a `_on_empirical_wizard_complete`; al cancelar navega de vuelta a `"formulario"`.
- **`_on_empirical_wizard_complete()`**: navega a `"formulario"` y llama `list_view.refresh()` en la vista cacheada para actualizar la tabla.
- **`_open_empirical_detail(observation_id)`**: abre `EmpiricalDetailModal` como `Toplevel` (modal blocking).
- **default_view para alumnos**: cambiado de `"inicio"` (placeholder) a `"formulario"` (funcional).

#### `scripts/launch_app.py`
- Agrega `SQLiteEmpiricalRepository`, `AppConfigRepository`, y los 4 use cases del formulario empírico.
- Construye `EmpiricalController` y lo pasa a `MainApplication`.
- Semilla de `station_uuid` en `app_config` si la DB es nueva (modo desarrollo, para no requerir onboarding completo).
- Simplificado el bloque de `create_uc` (ya no duplicaba la instancia).

---

## Arquitectura de navegación del formulario

```
sidebar "Formulario"
    └── _build_view("formulario")
            └── EmpiricalListView
                    ├── "+ Cargar observación" → _show_empirical_wizard()
                    │       └── EmpiricalWizardView (4 pasos)
                    │               ├── on_complete → refresh EmpiricalListView
                    │               └── on_cancel  → navigate("formulario")
                    └── doble-click / "Ver detalle" → _open_empirical_detail(obs_id)
                            └── EmpiricalDetailModal (Toplevel)
```

El wizard no se cachea (`_view_cache`): se crea fresco en cada apertura para garantizar que el state interno (spinboxes, checkboxes, eventos agregados) empiece limpio.

---

## Notas para fases posteriores

- **`inicio` (sidebar)**: sigue siendo placeholder. Para alumnos, la pantalla de inicio es ahora `formulario`. Si en el futuro se necesita una pantalla de bienvenida diferenciada, crear `InicioView` y cablearla en `_build_view("inicio")`.
- **`EmpiricalListView` muestra `user#<id>`** en la columna Observador en vez del nombre. El TODO está marcado en `list_view.py:176`. Para Fase 8.5b se necesita resolver el username a partir del `created_by_user_id` vía repo de usuarios.
- **`EmpiricalDetailModal`** es read-only por decisión de Fase 8.5a. Para Fase 8.5b se puede agregar botón "marcar discrepancia" para docentes.
- **`AppConfigRepository.get_station_uuid()`** lanza `RuntimeError` si la DB no tiene el valor. En producción, el onboarding siempre lo setea. En el launcher de desarrollo, el seed automático evita el error.
- **`EmpiricalWizardView` usa `ZoneInfo("America/Argentina/Buenos_Aires")`** internamente. Si el proyecto necesita soporte multi-zona, ese hardcode es el punto a cambiar.
