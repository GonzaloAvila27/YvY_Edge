# YVY

**Sistema meteorológico escolar offline-first para Instituciones de Educación Agropecuaria de Misiones.**

> El nombre "YVY" significa "tierra" en guaraní.

## ¿Qué es esto?

YVY es un sistema que captura datos meteorológicos en escuelas agropecuarias rurales con conectividad limitada. Combina:

- Lecturas automáticas de un sensor **WeatherStation WH1081** vía **pywws**.
- Carga manual de observaciones empíricas por parte de alumnos y docentes.
- Sincronización oportunística (cuando hay red) con un servidor central.
- Pipeline analítico Bronze/Silver/Gold para BI institucional.

El sistema está diseñado para funcionar **completamente offline** durante días o semanas, con sincronización automática al recuperarse la conectividad. Garantiza idempotencia end-to-end vía UUID v5 determinístico.

---

## Documentación

- 📋 **`docs/architecture/`** — Documentación de decisiones arquitectónicas.
- 📊 **`docs/diagrams/`** — Diagramas técnicos (12 SVG).
- 📖 **`docs/handbook/`** — Guía operativa para administradores y docentes.
- 📝 **`docs/historico/`** — Documentos previos al rediseño v3.

Documentos de referencia clave:

- `YVY_Anexo_Tecnico_v3.md` — anexo técnico institucional (entregable Ministerio).
- `YVY_Sistema_Local_v2.md` — anexo operativo con plan de fases.
- `YVY_Plan_Fases.md` — plan de implementación con prompts por fase.
- `YVY_Progreso_v1.md` — estado actual del proyecto.

---

## Requisitos

### Para desarrollo

- **Python 3.11+** (Debian 12 trae 3.11 por default).
- **Poetry** (gestor de deps): `curl -sSL https://install.python-poetry.org | python3 -`.
- **Git**.
- (Opcional) Sensor WH1081 conectado por USB para tests con hardware real.

### Para producción (netbook IEA)

- **Debian 12 Bookworm** o derivados (Ubuntu 22.04+).
- **Python 3.11+**, **systemd**, **chrony** (NTP).
- Sensor **Fine Offset WH1081** conectado por USB.
- Acceso de usuario al grupo `plugdev` (para USB sin sudo).

---

## Instalación (desarrollo)

```bash
# 1. Clonar repo
git clone https://github.com/<org>/yvy.git
cd yvy

# 2. Instalar Poetry (si no lo tenés)
curl -sSL https://install.python-poetry.org | python3 -

# 3. Instalar dependencias
poetry install

# 4. Configurar pre-commit hooks
poetry run pre-commit install

# 5. Copiar template de variables de entorno
cp .env.example .env
# editar .env con tus valores

# 6. Aplicar migraciones a la DB local
poetry run python -m yvy.cli migrate

# 7. Verificar instalación
poetry run pytest
```

## Instalación (netbook IEA)

Para deploy en una netbook escolar real, ver `deploy/README.md`. Resumen:

```bash
sudo bash deploy/install.sh
```

El script instala todo (Python, deps del SO, app, systemd service, chrony) y deja la app lista para ejecutar al boot.

---

## Comandos de desarrollo

```bash
# Correr la app
poetry run yvy

# Tests
poetry run pytest                    # todos
poetry run pytest -m unit            # solo unitarios (rápido)
poetry run pytest -m integration     # con DB
poetry run pytest -m e2e             # end-to-end completos
poetry run pytest --cov              # con coverage

# Lint y format
poetry run ruff check src/           # detectar issues
poetry run ruff check src/ --fix     # autofix
poetry run ruff format src/          # formatear

# Type checking
poetry run mypy src/yvy/domain       # estricto
poetry run mypy src/yvy/application  # estricto
poetry run mypy src/yvy              # todo el proyecto

# Pre-commit manual sobre todos los archivos
poetry run pre-commit run --all-files
```

---

## Estructura del proyecto

```
yvy/
├── src/yvy/                  # código fuente principal
│   ├── domain/               # capa pura: reglas de negocio (sin imports externos)
│   │   ├── shared/           # value objects, time utils, exceptions
│   │   ├── sensor/           # subdominio del sensor
│   │   ├── empirical/        # observaciones manuales
│   │   ├── comments/         # comentarios + eventos narrativos
│   │   ├── auth/             # roles y permisos
│   │   ├── sync/             # cola de sincronización
│   │   ├── help/             # HelpSystem (cross-platform core)
│   │   └── station/          # config de la estación
│   ├── application/          # capa de orquestación
│   │   ├── ports/            # interfaces (Protocol)
│   │   └── use_cases/        # casos de uso por subdominio
│   ├── infrastructure/       # adaptadores
│   │   ├── persistence/      # SQLite implementations
│   │   ├── pywws/            # adaptador del sensor
│   │   ├── sync/             # cliente HTTP + HMAC
│   │   ├── auth/             # bcrypt + sessions
│   │   ├── updates/          # UpdateManager
│   │   ├── system/           # NTP, USB, disk
│   │   ├── logging/          # config de logging
│   │   └── scheduling/       # threads daemon
│   ├── presentation/         # UI Tkinter
│   │   ├── components/       # widgets reutilizables
│   │   ├── views/            # pantallas completas
│   │   ├── help/             # Help UI específico Tkinter
│   │   └── controllers/      # mediadores View↔UseCase
│   ├── config/               # configuración global
│   └── main.py               # entry point
├── tests/                    # suite completa
│   ├── unit/                 # rápidos, sin DB
│   ├── integration/          # con DB real
│   ├── e2e/                  # flujo completo
│   └── property/             # property tests con hypothesis
├── migrations/               # SQL versionado
├── docs/                     # documentación
├── deploy/                   # scripts de instalación
├── data/                     # runtime (gitignored)
├── assets/                   # iconos, imágenes, fonts
└── scripts/                  # utilidades dev/ops
```

---

## Arquitectura en una mirada

```
┌─────────────────┐
│  Presentation   │  Tkinter (controllers + views)
└────────┬────────┘
         ↓
┌─────────────────┐
│  Application    │  Use cases + Ports (Protocol)
└────────┬────────┘
         ↓
┌─────────────────┐
│     Domain      │  Reglas de negocio puras
│  (no imports    │  Value objects, modelos, repos como Protocol
│   externos)     │
└────────┬────────┘
         ↑
┌─────────────────┐
│ Infrastructure  │  Adapters (SQLite, pywws, HTTP, bcrypt, NTP)
└─────────────────┘
```

Patrón: **DDD + Hexagonal Architecture**. El dominio es puro Python, sin dependencias externas. Las capas externas implementan interfaces (Protocol) que el dominio define.

---

## Estado del proyecto

Ver `docs/YVY_Progreso_v1.md` para estado detallado por tarea.

**Resumen al 26-Abr-2026:**
- ✅ Documentación técnica completa
- ✅ Schemas de base de datos cerrados (SQLite v8 + PostgreSQL central v2)
- ✅ 12 diagramas técnicos
- ✅ Especificación + mockups visuales (24 pantallas)
- ⏳ Implementación: Fase 0 en curso (bootstrap del repo)

---

## Licencia

Apache License 2.0 · Ver `LICENSE`.

---

## Contacto

Autor: Gonzalo Avila
Proyecto: YVY
Año: 2026