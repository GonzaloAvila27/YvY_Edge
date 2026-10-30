# Conflicto catchup vs. live source (LIBUSB_ERROR_ACCESS)

## Síntoma

```
usb1.USBErrorAccess: LIBUSB_ERROR_ACCESS [-3]
ERROR  yvy.presentation.controllers.sync_controller : Catchup falló
```

## Causa

pywws abre el dispositivo USB de manera **exclusiva** a través de libusb-1.0.
El daemon live (`PywwsLiveSource`) inicializa `WeatherStation()` al arrancar y
mantiene el handle abierto indefinidamente mientras escucha transmisiones del
sensor (cada ~48 s). Cuando el catchup intenta crear una segunda instancia de
`WeatherStation()`, libusb rechaza la apertura con `LIBUSB_ERROR_ACCESS [-3]`.

```
PywwsLiveSource.__init__ → WeatherStation() ← abierta, handle exclusivo
                                                         ↓
PywwsCatchupSource.__init__ → WeatherStation() ← ACCESS [-3] (dispositivo ya reclamado)
```

## Estado

Limitación conocida. El catchup **no puede correr mientras el daemon live está
activo** en la misma sesión de YVY. La app maneja el error de forma silenciosa
(log `ERROR`, UI no se bloquea).

## Opciones de fix (pendientes, por orden de complejidad)

| Opción | Descripción | Complejidad |
|---|---|---|
| A — Instancia compartida | Pasar el `WeatherStation` del live source al catchup (requiere refactor de puertos) | Media |
| B — Pausa live durante catchup | Señal al daemon live para que suelte el handle; catchup adquiere, lee, libera; live retoma | Media-alta |
| C — Catchup offline | Leer el buffer histórico en un proceso separado antes de iniciar el live daemon (solo en startup) | Baja |
| D — Importar desde CSV/pywws cache | No usar el buffer USB para catchup; depender de la exportación histórica de pywws | Media |

**Workaround actual**: el catchup se puede correr manualmente cuando la app
está cerrada (sin daemon live activo) mediante un script separado, o en el
arranque antes de que el live daemon capture el dispositivo.

## Archivos involucrados

| Archivo | Rol |
|---|---|
| `src/yvy/infrastructure/pywws/live_source.py` | Abre y mantiene `WeatherStation` para live |
| `src/yvy/infrastructure/pywws/catchup_source.py` | Intenta abrir segunda `WeatherStation` |
| `src/yvy/presentation/controllers/sync_controller.py` | Orquesta live + catchup, captura el error |
| `src/yvy/application/use_cases/sensor/run_catchup_recovery.py` | Use case de catchup |
