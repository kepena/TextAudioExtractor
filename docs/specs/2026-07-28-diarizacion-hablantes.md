# Spec — Diarización de hablantes (Camino C: whisperX)

- **Fecha:** 2026-07-28
- **Estado:** ✅ aprobado por Kike (2026-07-28)
- **Origen:** brainstorm 2026-07-28 (Camino C elegido). Feature del alcance
  "por decidir, no descartado" del proyecto.

## 1. Overview

Añadir **diarización de hablantes** a TextAudioExtractor: además de *qué* se dijo,
marcar *quién* lo dijo y cuándo. Se activa a demanda (`--diarize` en CLI, checkbox
en la GUI); apagado por defecto, el motor se comporta exactamente como hoy. Cuando
se activa, un pipeline basado en **whisperX** transcribe, alinea palabra-a-palabra
y separa hablantes en una sola pasada. Las salidas `.srt` y `.txt` prefijan cada
intervención con una etiqueta genérica (`SPEAKER_00`, `SPEAKER_01`). Todo corre
local (invariante 1).

## 2. Usuarios específicos

- **Kike, uso interno de Kaiketek** al arranque. Casos concretos:
  - Sesiones de terapia 1-a-1 y entrevistas (2 voces, turnos claros) — el caso
    principal y el que mejor sale.
  - Reuniones y llamadas de venta con 3+ personas — soportado, con la advertencia
    de que la separación se equivoca más.
- El día que esto sea producto, el mismo motor sirve; el MVP no diseña para un
  cliente externo todavía.

## 3. Contexto del problema

Hoy el `.srt`/`.txt` es un muro de texto continuo: en una sesión de terapia o una
entrevista no se distingue quién habló. Releer o analizar una transcripción larga
obliga a reconstruir a mano los turnos.

Whisper entrega texto con tiempos pero sin identidad de voz. Separar hablantes es
un paso distinto (diarización) que hay que cruzar con la transcripción. whisperX ya
integra transcripción + alineación + diarización, así que es el camino con menos
"pegamento" propio que mantener.

## 4. Alcance versión 1

### Incluye

- **Flag opt-in**, apagado por defecto:
  - CLI: `--diarize` en `tae local` y en `tae url`.
  - GUI: checkbox "Identificar hablantes".
- **Pipeline whisperX** solo cuando `--diarize` está activo: transcribe, alinea y
  diariza el audio.
- **Pista opcional del nº de hablantes**: `--speakers N` (CLI) / campo numérico
  (GUI). Vacío = detección automática. Fijarlo mejora la precisión cuando se sabe
  (ej. terapia = 2).
- **Etiquetas genéricas** en las salidas: `SPEAKER_00`, `SPEAKER_01`, … asignadas
  por orden de aparición.
  - `.srt`: cada bloque con `SPEAKER_00: <texto>` en la línea de texto.
  - `.txt`: una línea por intervención, prefijada `SPEAKER_00: <texto>`; se inserta
    una línea en blanco cuando cambia el hablante, para que sea escaneable.
- **`Segment` gana un campo `speaker` opcional.** Cuando no se diariza, queda
  vacío y las salidas se ven idénticas a hoy.
- **Degradado sin GPU** (invariante 3): si no hay GPU NVIDIA, corre en CPU con
  aviso de que será lento; no crashea.
- **Dependencia de setup del token HF** (invariante 5): los pesos de diarización
  (pyannote, vía whisperX) se descargan una vez tras aceptar términos en
  HuggingFace con un token gratuito. En runtime nada sale a la nube. Si falta el
  token o no se aceptaron los términos, error claro con instrucciones — no un
  traceback.

### No incluye (fuera de la V1)

- **Renombrar hablantes** (`SPEAKER_00` → "Kike"). Las etiquetas quedan genéricas;
  mapear nombres sería una capa de GUI posterior.
- **Identificar personas reales** entre videos (huellas de voz / speaker ID). Cada
  video numera desde cero; `SPEAKER_00` de un video no es el de otro.
- **Diarizar subtítulos incrustados o auto-generados.** Esas pistas no traen
  identidad de voz. Ver §5 para qué pasa si se pide `--diarize` con subtítulos
  disponibles.
- **Reemplazar el camino de transcripción actual.** Sin `--diarize`, se usa el
  `transcribe.py` de hoy (faster-whisper), ya verificado en GPU, intacto.
- **Editar el video, traducción, transcripción en la nube** (invariantes 1 y 2).

## 5. Comportamiento esperado

### Flujo base (local, video con voz)

1. Kike corre `tae local sesion.mp4 --diarize` (o marca el checkbox en la GUI).
2. El sistema avisa la etapa: extrae audio → transcribe+alinea → separa hablantes.
   Reporta progreso como hoy.
3. Al terminar, `.srt` y `.txt` traen las intervenciones prefijadas por hablante.
4. El resumen final indica cuántos hablantes se detectaron (ej. "2 hablantes").

### `--diarize` cuando hay subtítulos disponibles

La diarización necesita el audio; los subtítulos incrustados/auto no sirven. Por
eso **`--diarize` implica transcribir el audio** aunque existan subtítulos: el
sistema avisa ("Ignoro los subtítulos incrustados: para identificar hablantes
transcribo el audio") y procede. *(Decisión a confirmar — ver §7.)*

### Nº de hablantes

- Sin `--speakers`: whisperX estima el número. Puede equivocarse con audio ruidoso
  o solapamientos.
- Con `--speakers N`: se le fija el número; útil y recomendado cuando se conoce.

### Online (`tae url --diarize`)

Igual que el local: tras descargar, si se pidió `--diarize`, se transcribe y
diariza el audio (ignorando subtítulos del creador). En **playlist**, aplica a cada
video del lote; un fallo de diarización en un video se clasifica y no aborta el
lote (coherente con el comportamiento actual del módulo online).

### GUI

- Checkbox "Identificar hablantes" + campo opcional "Nº de hablantes".
- Al activarlo, si el video tenía subtítulos, la GUI muestra el mismo aviso de que
  se transcribirá el audio.
- Sin GPU, muestra el aviso de lentitud antes de arrancar, como hoy con Whisper.

### Cómo se ven las salidas (ejemplo)

`.srt`:

```
1
00:00:01,200 --> 00:00:04,500
SPEAKER_00: Cuéntame cómo te sentiste esta semana.

2
00:00:04,900 --> 00:00:09,100
SPEAKER_01: Al principio con mucha ansiedad, pero fue bajando.
```

`.txt`:

```
SPEAKER_00: Cuéntame cómo te sentiste esta semana.

SPEAKER_01: Al principio con mucha ansiedad, pero fue bajando.
```

## 6. Posibles errores y mitigaciones

| Situación | Qué ve el usuario |
|---|---|
| **Token HF ausente / términos no aceptados** | Mensaje claro: qué modelo aceptar, dónde sacar el token gratis y cómo configurarlo. No corre a medias ni suelta traceback. |
| **Sin GPU NVIDIA** | Aviso de que la diarización correrá en CPU y será lenta; procede igual (invariante 3). |
| **Un solo hablante detectado** | Se etiqueta todo como `SPEAKER_00`; resultado válido, no es un error. |
| **Solapamiento de voces / audio ruidoso** | Puede asignar mal algún turno. Se documenta como límite conocido; `--speakers N` ayuda. Sin mecanismo de corrección manual en la V1. |
| **Audio sin voz (solo música/silencio)** | No hay hablantes que separar; se comporta como transcripción vacía actual, con aviso. |
| **Primera corrida: descarga de pesos grande** | Aviso de que se están descargando los modelos (como ya pasa con los modelos Whisper). |
| **Cancelación a medias** | Corta limpio entre etapas, igual que el pipeline actual; no deja salidas parciales corruptas. |
| **`--diarize` sobre video sin audio** | Error claro "no hay audio que diarizar", sin intentar el pipeline. |
| **whisperX no instalado** | Error claro tratándolo como dependencia de setup (invariante 5), con cómo instalarlo. |

## 7. Decisiones resueltas (aprobadas 2026-07-28)

1. **`--diarize` con subtítulos disponibles** → **fuerza transcripción del audio y
   avisa**. La diarización no funciona sobre subtítulos; con `--diarize` se ignoran
   los subtítulos incrustados/auto y se transcribe el audio.
2. **Formato de etiqueta en `.txt`** → `SPEAKER_00: texto`, con línea en blanco al
   cambiar de hablante.
3. **whisperX solo con `--diarize`** → no se unifica todo bajo whisperX en esta
   versión. Sin el flag, se usa el `transcribe.py` actual (faster-whisper) intacto.
```
