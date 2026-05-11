# Recupero de datos del sensor

El sensor WH1081 **bufferea internamente** las últimas lecturas: cuando la PC servidor está apagada o YVY no estaba corriendo, la consola igual sigue grabando datos.

El **recupero** (catchup recovery) es el proceso que **descarga ese buffer** de la consola y lo incorpora a la base de datos.

## Cuándo ejecutarlo

- Después de un **corte de luz prolongado**.
- Después de **reiniciar la PC servidor**.
- Si notás un **hueco** en el dashboard (por ejemplo, faltan datos de la madrugada).
- **Una vez por semana como rutina**, aunque no sospeches nada.

## Cómo ejecutarlo

1. En el menú lateral, ir a **Sync**.
2. Click en **Ejecutar recupero**.
3. Confirmar.
4. Esperar a que termine. Puede tardar de **30 segundos a 5 minutos** dependiendo de cuánto haya buffeado.

## Qué pasa durante el recupero

- El sistema **bloquea** la ejecución concurrente: no se puede correr dos al mismo tiempo.
- Las lecturas que ya tenés **NO se duplican**: el sistema usa identificadores deterministas para detectar y descartar duplicados.
- La carga manual de observaciones **sigue funcionando** durante el recupero.

## Si falla

Errores típicos y qué hacer:

- **"Bloqueo de ejecución activo"**: hay otro recupero corriendo. Esperá unos minutos.
- **"Sensor no responde"**: revisá el cable USB y la consola. Ver el artículo *El sensor no manda datos*.
- **"Error de parseo"**: contactá al soporte técnico, pasale los Logs del momento del error.

---

*Contenido provisorio — pendiente de revisión técnica.*
