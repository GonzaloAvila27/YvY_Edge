# YVY Edge

[![CI](https://github.com/GonzaloAvila27/YvY_Edge/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/GonzaloAvila27/YvY_Edge/actions/workflows/ci.yml)

**Nodo local de estación meteorológica escolar, offline-first, para las Instituciones de Educación
Agropecuaria (IEA) de Misiones, Argentina.**

> "YVY" significa "tierra" en guaraní. Este repositorio contiene **YVY Edge**, el componente que corre
> en la netbook de cada escuela. El servidor central, **YVY Core**, es un sistema aparte.

YVY Edge es una aplicación de escritorio **Python 3.12 + Tkinter** que:

- lee una estación meteorológica **Fine Offset WH1081** por USB;
- guarda todo localmente en **SQLite**, y sigue funcionando días o semanas sin internet;
- registra observaciones y eventos meteorológicos cargados por docentes y alumnos;
- envía los datos a YVY Core, firmados con **HMAC-SHA256**, cuando hay conexión;
- se actualiza sola (OTA), con rollback automático si la versión nueva no arranca.

**Versión actual: `1.6.0`** (rama `main`).

---

## Por dónde empezar

| Si querés… | Leé |
|---|---|
| Entender qué es, instalarlo y correrlo | [`yvy/README.md`](yvy/README.md) |
| Ver cómo está construido | [`yvy/docs/ARQUITECTURA_ACTUAL.md`](yvy/docs/ARQUITECTURA_ACTUAL.md) |
| Encontrar un componente, archivo o función | [`yvy/docs/MAPA_DEL_CODIGO.md`](yvy/docs/MAPA_DEL_CODIGO.md) |
| Instalarlo en una escuela | [`yvy/docs/MANUAL_INSTALACION_EDGE.md`](yvy/docs/MANUAL_INSTALACION_EDGE.md) |
| Saber qué cambió en cada versión | [`yvy/CHANGELOG.md`](yvy/CHANGELOG.md) |
| Conocer el estado técnico y los problemas conocidos | [`yvy/docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md`](yvy/docs/RELEVAMIENTO_TECNICO_EDGE_2026-09.md) |
| Ver las certificaciones | [`yvy/docs/CERTIFICACION_ARQUITECTONICA_2026-07.md`](yvy/docs/CERTIFICACION_ARQUITECTONICA_2026-07.md) · [`yvy/docs/ACTA_CERTIFICACION_OTA_1.5.x.md`](yvy/docs/ACTA_CERTIFICACION_OTA_1.5.x.md) |

---

## Inicio rápido (desarrollo)

Todo el proyecto vive en la carpeta `yvy/`:

```bash
cd yvy
poetry install

poetry run python -m yvy migrate          # crea / actualiza la base local
poetry run python scripts/launch_app.py   # abre la GUI
poetry run python -m yvy status           # diagnóstico por consola

poetry run pytest                         # tests
```

Para instalar en una netbook de escuela (Windows 10, por pendrive), seguí el
[manual de instalación](yvy/docs/MANUAL_INSTALACION_EDGE.md).

---

## Estructura del repositorio

```
├── .github/workflows/ci.yml   CI: ruff (lint + formato), reglas de arquitectura, mypy
├── yvy/                       el proyecto YVY Edge (código, tests, migraciones, scripts, docs)
└── yvy_*.md, yvy_*.toml,      archivos del arranque inicial (Fase 0), sólo como registro
    yvy_fase0_bootstrap.tar.gz histórico; no los usa el proyecto actual
```

### Ramas

| Rama | Contenido |
|---|---|
| `main` | rama principal: versión vigente (`1.6.0`) |
| `master`, `stab/ini-1-higiene` | ramas de trabajo de la estabilización 1.6.0, ya integradas en `main` |

---

## Integración continua

El workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) corre en cada push y pull request:

1. **Ruff**: lint y formato.
2. **Reglas arquitectónicas**: `yvy/scripts/check_arch_rules.py`.
3. **mypy**: tipos de `domain`, `application`, `infrastructure` y `cli`.

La suite de tests (`pytest`) **no** corre en CI: se ejecuta localmente.

---

## Autor

**Gonzalo Rubens Avila** · Proyecto YVY · Pasantía INET / Ministerio de Educación / CGE Misiones · 2026
