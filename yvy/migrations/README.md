# Migrations

Migraciones SQL versionadas para la base de datos local SQLite.

## Convención de naming

```
NNN_descripcion_corta.sql
```

- `NNN`: número incremental con padding (001, 002, 003, ...).
- `descripcion_corta`: snake_case, descriptivo.

## Cómo se aplican

Se aplican en orden ascendente. La aplicación registra cada migración en la
tabla `schema_version` con su `version` y `applied_at`.

Comando:

```bash
poetry run python -m yvy.cli migrate
```

## Rollback

**No hay rollback automático.** Las migraciones son forward-only.

Si una migración rompe algo en dev, la solución es:
1. Restaurar el archivo `data/yvy.sqlite` desde backup.
2. Corregir la migración.
3. Re-aplicar.

En producción, las migraciones se prueban en staging primero.

## Estado actual

- `001_initial_v8.sql` — Schema inicial v8 (13 tablas, UUID v5, retención
  configurable, pywws_mode). **Pendiente de copiar desde
  `YVY_Local_IEA_v8.sql` en Fase 2.**
