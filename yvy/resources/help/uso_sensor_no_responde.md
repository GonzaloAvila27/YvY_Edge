# El sensor no manda datos

Si el indicador de **Sensor** en la barra superior está en rojo o ámbar, las lecturas automáticas no están llegando.

## Diagnóstico rápido

Verificá en orden:

1. **¿La consola del sensor está prendida?** El display LCD del WH1081 debe mostrar valores actuales.
2. **¿Las pilas o el adaptador están bien?** Si el LCD está apagado o parpadeando, hay problema de energía.
3. **¿El cable USB está conectado a la PC?** Tiene que estar en la PC servidor (la que corre YVY).
4. **¿La PC servidor está prendida y con YVY corriendo?** YVY debe estar abierto, aunque sea minimizado.

## Cuándo es normal

El sensor de exterior **transmite cada 48 segundos** a la consola. Si la consola está bien pero YVY tarda 2-3 minutos en actualizar, es normal: el sistema bufferea lecturas y las procesa por lotes.

## Cuándo NO es normal

- Estado en rojo durante **más de 10 minutos** con todo lo anterior verificado.
- Mensajes de error en el área de notificaciones.
- Indicador de NTP también en rojo (puede indicar problema más amplio del sistema).

## Qué hacer

Si después de revisar todo lo anterior el sensor sigue sin responder:

1. Ejecutá un **recupero de datos** (si sos admin, te aparece la opción en Sync). Esto recupera las lecturas que la consola tiene buffeadas.
2. Si el problema persiste, contactá al técnico de soporte de YVY indicando hace cuánto está caído.

---

*Contenido provisorio — pendiente de revisión técnica.*
