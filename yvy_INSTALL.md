# Instalación de YVY · Guía para administradores de IEA

Esta guía está pensada para el administrador técnico de cada Institución de
Educación Agropecuaria. **No se requiere conocimiento previo de Python ni de
desarrollo de software.**

---

## Antes de empezar — checklist

Antes de instalar YVY, verificar que la netbook cumple:

- [ ] **Sistema operativo:** Debian 12 Bookworm o Ubuntu 22.04+ instalado.
- [ ] **Conexión a internet:** disponible al menos durante la instalación
      (después la app puede funcionar offline).
- [ ] **Permisos de administrador:** acceso `sudo` en la netbook.
- [ ] **Sensor WH1081:** físicamente disponible (puede conectarse después).
- [ ] **Código de activación:** recibido del Ministerio (formato: 8 caracteres
      alfanuméricos).

---

## Instalación rápida (un solo comando)

```bash
curl -fsSL https://yvy-central.misiones.gob.ar/install.sh | sudo bash
```

> ⚠️ Este comando todavía no está disponible. Lo estará al cerrar la Fase 13
> del plan de implementación. Por ahora seguir la **instalación manual** abajo.

---

## Instalación manual (paso a paso)

### Paso 1 — Verificar Python 3.11

Abrir terminal y correr:

```bash
python3 --version
```

Si la respuesta es `Python 3.11.x` o superior, **OK, seguir al paso 2**.

Si la versión es menor o el comando no existe:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 --version
```

### Paso 2 — Instalar dependencias del sistema operativo

```bash
sudo apt update
sudo apt install -y \
    git \
    curl \
    sqlite3 \
    libusb-1.0-0 \
    chrony \
    build-essential \
    python3-dev \
    libffi-dev
```

### Paso 3 — Configurar NTP (sincronización de tiempo)

YVY requiere que el reloj de la netbook esté sincronizado con servidores
de tiempo. Configurar `chrony` con servidores argentinos:
tar -xzf yvy_fase0_bootstrap.tar.gz
```bash
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.backup
sudo tee /etc/chrony/chrony.conf > /dev/null << 'EOF'
# Servidores NTP argentinos
server tiempo.ar.gov.ar iburst
server ntp.shoa.cl iburst
pool 0.south-america.pool.ntp.org iburst

# Configuración estándar
driftfile /var/lib/chrony/chrony.drift
makestep 1.0 3
rtcsync
EOF

sudo systemctl restart chrony
sudo systemctl enable chrony
```

Verificar que está funcionando:

```bash
chronyc tracking
```

Debería mostrar `System time : ...` con un valor pequeño (ms).

### Paso 4 — Permisos de USB para el sensor

El usuario que ejecutará YVY necesita acceso al sensor WH1081 sin sudo:

```bash
sudo usermod -a -G plugdev $USER
```

> Después de este comando, **cerrar sesión y volver a entrar** para que el
> cambio tome efecto.

### Paso 5 — Instalar Poetry (gestor de dependencias Python)

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Agregar Poetry al PATH (en `~/.bashrc`):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Verificar:

```bash
poetry --version
```

### Paso 6 — Clonar el repositorio de YVY

```bash
cd ~
git clone https://github.com/<org>/yvy.git
cd yvy
```

### Paso 7 — Instalar la app

```bash
poetry install
```

Este comando descarga e instala todas las dependencias Python necesarias.
Puede tardar varios minutos la primera vez.

### Paso 8 — Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Editar el archivo `.env` con los valores específicos de tu IEA:

```ini
YVY_ENV=prod
YVY_SERVER_URL=https://yvy-central.misiones.gob.ar
YVY_API_KEY=<tu_api_key_de_activacion>

# IMPORTANTE: el bootstrap del superadmin requiere clave fuerte
YVY_SUPERADMIN_USER=admin_local
YVY_SUPERADMIN_PASS=<una_clave_fuerte_aqui>
```

Guardar con `Ctrl+O`, salir con `Ctrl+X`.

### Paso 9 — Aplicar migración inicial de base de datos

```bash
poetry run python -m yvy.cli migrate
```

### Paso 10 — Probar que arranca

```bash
poetry run yvy
```

Si todo está correcto, debería abrirse el wizard de onboarding o la app
principal.

---

## Instalación como servicio systemd (auto-start al boot)

Para que YVY arranque automáticamente cuando se enciende la netbook:

```bash
sudo cp deploy/yvy-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable yvy-app
sudo systemctl start yvy-app
```

Verificar:

```bash
sudo systemctl status yvy-app
```

Ver logs en tiempo real:

```bash
sudo journalctl -u yvy-app -f
```

---

## Resolución de problemas comunes

### "command not found: poetry" después de instalar

El PATH no se actualizó. Solución:

```bash
source ~/.bashrc
# o reiniciar la terminal
```

### "permission denied" al conectar el sensor USB

El usuario no está en el grupo `plugdev`, o no se reinició la sesión:

```bash
groups | grep plugdev   # debe mostrar plugdev
```

Si no aparece, repetir Paso 4 y reiniciar sesión.

### El sensor no se detecta

Verificar que el sensor está conectado:

```bash
lsusb | grep -i fine
```

Debería mostrar algo como `Fine Offset Electronics WH-3080 Weather Station`.

Si no aparece:
1. Probar otro puerto USB.
2. Verificar el cable USB.
3. Reiniciar la netbook.

### Errores al instalar deps Python

Si `poetry install` falla con errores de compilación:

```bash
sudo apt install -y python3-dev build-essential libffi-dev libssl-dev
poetry install
```

---

## ¿Necesitás ayuda?

- **Documentación técnica:** `docs/`
- **Logs de la app:** `data/logs/yvy.log`
- **Logs del sistema:** `journalctl -u yvy-app`
- **Soporte:** contactar a tu coordinador del proyecto en INET / Ministerio.
