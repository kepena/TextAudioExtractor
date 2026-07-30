# Spec — Cancelar inmediato (P12)

- **Fecha:** 2026-07-30
- **Estado:** ✅ aprobado por Kike (2026-07-30)
- **Origen:** verificación de GUI de la diarización (2026-07-29). Un video de 84 min
  destapó que "Cancelar" no corta hasta que termina la etapa en curso.
- **Pendiente:** P12 en [docs/pendientes.md](../pendientes.md).

## 1. Overview

Hacer que el botón **Cancelar** de la GUI detenga la corrida **de inmediato**, sin
importar en qué etapa esté. Hoy la cancelación es cooperativa (solo se consulta entre
etapas), así que en la diarización de un archivo largo el usuario pulsa Cancelar y la
app sigue trabajando varios minutos como si estuviera congelada. La solución acordada
(opción A del brainstorm): correr el motor en un **subproceso** que la GUI mata al
cancelar — corte inmediato y limpio, sin arriesgar el estado de torch/CUDA del proceso
de la interfaz.

## 2. Usuarios específicos

- **Kike, en la GUI de escritorio**, procesando un video largo (típicamente una
  sesión de terapia o entrevista de 30-90 min) con "Identificar hablantes" activo.
  Es quien pulsa Cancelar cuando se da cuenta de que cargó el archivo equivocado, que
  va a tardar demasiado, o que quiere cambiar una opción.

## 3. Contexto del problema

La diarización corre en CPU y es lenta. whisperX hace tres llamadas nativas
monolíticas (transcribir → alinear → separar hablantes) que Python no puede
interrumpir desde dentro. La cancelación actual solo se revisa **entre** esas etapas.

Resultado observado (prueba real, video de 84 min): al pulsar Cancelar, la app mostró
"Cancelando…" y siguió ocupada minutos, con los controles bloqueados, indistinguible
de estar colgada. En un video corto no se nota; en uno largo es una mala experiencia y
puede llevar a matar la app a la fuerza.

## 4. Alcance versión 1

### Incluye

- **La GUI corre el trabajo del motor en un subproceso separado.** Al pulsar Cancelar,
  la GUI **termina ese subproceso**, y la corrida se detiene de inmediato.
- **Aplica a todos los jobs del motor lanzados desde la GUI**: video local y online
  (URL/playlist), tanto transcripción normal como diarización. Así el Cancelar es
  uniforme, no solo responsivo en unos flujos y en otros no. *(Decisión a confirmar —
  §7.)*
- **Objetivo de respuesta:** la corrida se detiene en **≤ ~2 segundos** desde el clic,
  en cualquier etapa (incluida la mitad de una transcripción larga).
- **La GUI queda estable** tras cancelar: sin crash, controles reactivados, listo para
  una nueva corrida.
- **Progreso y etapas siguen llegando** a la barra y a las etiquetas mientras el
  subproceso trabaja (el usuario no pierde el feedback que ya tiene hoy).
- **Sin restos**: al cancelar no quedan archivos de salida a medias que parezcan
  válidos, ni temporales huérfanos en disco.

### No incluye (fuera de la V1)

- **La CLI.** En la terminal, Ctrl+C (o cerrar la ventana) ya mata el proceso entero,
  incluidas las llamadas nativas, así que el corte inmediato ya existe ahí. No se
  cambia la CLI. *(Decisión a confirmar — §7.)*
- **Pausar/reanudar** una corrida. Cancelar es detener, no pausar.
- **Cancelación parcial** (p. ej. quedarse con lo transcrito hasta el corte). Al
  cancelar no se entrega salida parcial.
- **Cambiar el motor o el modelo de diarización.** Esto es solo cómo se detiene, no
  qué se ejecuta.

## 5. Comportamiento esperado

### Flujo normal de cancelación

1. El usuario tiene una corrida en curso (barra avanzando, etiqueta de etapa, botón
   Cancelar activo, resto de controles bloqueados) — igual que hoy.
2. Pulsa **Cancelar**.
3. En ≤ ~2 s la app muestra el mensaje de cancelado (el actual: "Cancelado. No se
   generaron archivos válidos."), la barra vuelve a 0, y los controles se reactivan.
4. No se generó ningún archivo de salida de esa corrida.
5. La app queda lista para cargar otro archivo o volver a intentar, sin reiniciarla.

### Durante la corrida (sin cambios visibles)

- La barra de progreso y las etiquetas de etapa ("Transcribiendo e identificando
  hablantes…", "Cargando modelos…", etc.) siguen mostrándose como hoy. El hecho de que
  el trabajo ocurra en un subproceso es invisible para el usuario mientras todo va bien.

### Cancelar en una playlist (online)

- Si se cancela a mitad de un lote, se detiene de inmediato el video en curso y no se
  procesan los siguientes. Los videos ya terminados del lote conservan sus salidas
  (coherente con el comportamiento actual del lote).

## 6. Posibles errores y mitigaciones

| Situación | Qué ve / obtiene el usuario |
|---|---|
| **El subproceso muere solo** (crash del motor, falta de memoria) | La GUI lo detecta y muestra un error claro ("No se pudo completar…"), sin quedarse colgada esperando. |
| **Cancelar justo cuando el job estaba terminando** (carrera) | Resultado coherente: o se completó (muestra "Listo" con archivos) o se canceló (sin archivos); nunca un estado ambiguo ni archivos a medias. |
| **Temporales huérfanos** al matar el subproceso a media descarga/extracción | La app limpia la carpeta temporal de esa corrida; no se acumulan temporales en disco tras un cancelar. |
| **GPU/CUDA ocupada** por el trabajo matado | Al ser un proceso aparte, matarlo libera su contexto de GPU/CPU limpiamente; el proceso de la GUI nunca queda con torch/CUDA en mal estado. |
| **Cerrar la ventana con una corrida activa** | Se detiene el subproceso igual que un Cancelar; no queda un proceso del motor huérfano trabajando en segundo plano. |
| **Reintentar inmediatamente tras cancelar** | La nueva corrida arranca limpia; la cancelación anterior no deja el motor a medio cargar. |

## 7. Decisiones resueltas (aprobadas 2026-07-30)

1. **Alcance = GUI solo.** La CLI no se toca: Ctrl+C (o cerrar la terminal) ya mata el
   proceso entero, incluidas las llamadas nativas.
2. **Cubre todos los jobs del motor desde la GUI** (local + online, transcribir +
   diarizar), no solo la diarización, para que el Cancelar sea uniforme.
3. **Al cerrar la ventana** con una corrida activa, se cancela automáticamente el
   subproceso (no se pide confirmación aparte).
