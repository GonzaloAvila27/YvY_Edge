# OTA — fixes de la arquitectura de slots (1.5.1)

Hallazgos y correcciones del **primer test OTA end-to-end** (instalación manual
1.5.1 → OTA a dummies). El test cumplió su propósito: cazó bugs catastróficos
**antes** de cualquier despliegue real.

---

## 1. Pérdida de datos post-OTA (CRÍTICO) — corregido

### Síntoma
La actualización "completaba" pero la app arrancaba como instalación limpia:
sin usuarios, sin credenciales, DB vacía. Había que recrear el superusuario.

### Causa raíz
`launch_app.py` derivaba **un solo** `ROOT = Path(__file__).parents[1]` y lo usaba
para TODO. Post-OTA la app corre desde el slot
(`C:\YVY\releases\<ver>\scripts\launch_app.py`), así que `parents[1]` = **el slot**,
no `C:\YVY`. En consecuencia:

```
db_path     = C:\YVY\releases\<ver>\data\yvy.sqlite   <- VACIO
credentials = C:\YVY\releases\<ver>\data\station_credentials.json
UpdateInstaller / releases / current.txt -> todo apuntando al slot
```

La DB real (`C:\YVY\data\yvy.sqlite`) quedaba **intacta pero ignorada**. En flat
(`parents[1]` = `C:\YVY`) todo coincidía; el bug solo aparece en modo slot, por eso
recién se vio en el primer OTA exitoso.

### Fix
Separar **CODE_ROOT** (slot — código/recursos) de **STABLE_ROOT** (`C:\YVY` —
datos persistentes). Helper único:
`yvy.infrastructure.system.paths.resolve_stable_root` — si el code root es un slot
(`.../releases/<ver>`), el root estable es el que contiene `releases/`; override por
env `YVY_ROOT`.

- `launch_app.py`: `STABLE_ROOT` para data/credentials/logs/releases/installer;
  `CODE_ROOT` para `src/` y `resources/`. `build_core_dependencies` ahora recibe
  `migrations_dir=CODE_ROOT/migrations` (migraciones del slot) con `db_path` estable.
- `bootstrap.py`: nuevo parámetro `migrations_dir` (separa DB estable de migraciones del slot).
- `cli/__main__.py`: `_find_repo_root` también resuelve al root estable (el CLI leía
  la DB vacía del slot tras un OTA).
- Tests: `tests/unit/infrastructure/system/test_paths.py`.

---

## 2. INSTALL_UPDATE.bat — encoding y heredocs (corregido)

### 2a. El `.bat` no parseaba (cmd ejecutaba fragmentos)
**Causa:** line endings **LF** (444 LF / 0 CRLF) + `chcp 65001` + caracteres de caja
`─`/`═` en comentarios. La tríada desincroniza el parser de cmd → comentarios `::`
ejecutados como comandos, variables truncadas (`python`→`thon`).
**Fix:** CRLF + ASCII puro (box-drawing → `=`/`-`, acentos → base) + se quitó `chcp 65001`.

### 2b. 3 bloques `python -c "..."` multilínea (corregido)
**Causa:** cmd no puede pasar un argumento entre comillas a través de varias líneas;
el código Python (pasos 8/retención, rollback, migrate-flat) se ejecutaba como
comandos batch (`from`, `import`, `ReleaseRetention` "no se reconoce").
**Fix:** los 3 bloques se movieron a `scripts/_install_hooks.py` (subcomandos
`post-install` / `migrate-flat` / `mark-rollback`, no-fatales) y el `.bat` los llama
**en una sola línea**. Pasa `--root %YVY_ROOT%` (estable) y `--version`.

> El `.bat` está **excluido del tar** (no se auto-reemplaza). Se despliega a
> `C:\YVY\INSTALL_UPDATE.bat` desde `dist/usb` o a mano. `_install_hooks.py` sí viaja
> en el tar (vive en `scripts/`).

---

## 3. Botón "INSTALAR" gris (analizado — pendiente de re-test)

### Mecanismo (confirmado)
`update_modal.py:169`:
```python
can_install = self._user_role in _ADMIN_ROLES and is_downloaded
install_btn = ttk.Button(..., state="normal" if can_install else "disabled")
```
`is_downloaded` viene del snapshot `update_info` al abrir el modal
(`is_update_downloaded()` → flag `update_pending.downloaded`). La campana se enciende
con `pending AND is_downloaded` (`app.py:712`).

### Hipótesis principal
La inconsistencia "campana activa (descargado) pero botón gris" es muy probablemente
**consecuencia del bug #1**: con el aislamiento de datos roto, el flag
`update_pending.downloaded` y su lectura podían caer en `data/` distintos según el
path (GUI en slot vs descarga/CLI con otro root). El fix #1 hace que **todos** los
caminos compartan `C:\YVY\data`, lo que debería volver consistente el flag.

### Recomendado (no aplicado — verificar tras re-test con el fix #1)
- Re-correr el OTA con el fix de aislamiento puesto y observar si el botón ya habilita.
- Si persiste: que el modal recompute `is_update_downloaded()` en vivo al renderizar
  el botón y/o se refresque al completar la descarga (hoy es snapshot único).
- Mientras tanto, la instalación se dispara igual desde la notificación de la campana.

---

## Empaquetado
Fixes #1 y #2 entran en **1.5.1** (rebuild del manual + dummies 1.5.3/1.5.4).
El `.bat` corregido se despliega al root del nodo (no viaja en el tar).
