# Spec — Módulo Online (YouTube/plataformas) · Fase 4

- **Fecha:** 2026-07-27
- **Fase:** 4 (módulo `online`, capa aislada sobre el motor)
- **Estado:** aprobado (2026-07-27) — listo para `k-planner`

## 1. Overview

TextAudioExtractor hoy solo procesa videos que ya están en disco. Esta fase añade
una capa aislada (`src/tae/online/`) que, dada una **URL** de YouTube u otra
plataforma soportada por `yt-dlp`, descarga la fuente, reutiliza el motor existente
y entrega las mismas salidas de siempre: **texto plano**, **`.srt` con timestamps**
y **audio**. Se expone como un nuevo comando `tae url <URL>`. Soporta procesar una
**playlist completa en lote**. Sigue el principio del proyecto: la red se usa solo
para traer la fuente; audio y video nunca salen a un tercero para transcribir.

## 2. Usuarios Específicos

- **Uso primario:** el equipo interno de Kaiketek (Kike y quien opere la herramienta)
  que necesita sacar el texto y el audio de un video que está en YouTube/online sin
  tener que descargarlo a mano primero.
- **Contexto de uso:** desde la **CLI**, en una máquina Windows con GPU NVIDIA
  (supuesto de rendimiento, no requisito — invariante 3). Puede dejarse corriendo
  **desatendido** para procesar una playlist entera.
- **Fuera de este usuario:** esta fase **no** toca la GUI. El módulo online arranca
  como CLI; integrarlo a la interfaz es una fase posterior.

## 3. Contexto del Problema

Hoy, para procesar un video de YouTube hay que: (1) descargarlo con otra
herramienta, (2) encontrar el archivo, (3) pasarlo al motor local. Es manual,
propenso a error y no escala cuando son varios videos o una playlist. Además,
muchos videos **ya traen subtítulos** subidos por el creador: transcribirlos con
Whisper cuando ya existe un texto oficial desperdicia tiempo y GPU. El módulo online
elimina el paso manual y aprovecha los subtítulos existentes cuando los hay.

## 4. Alcance Versión 1

### Incluye

- Comando nuevo `tae url <URL>` que acepta una URL de video **o** de playlist.
- Descarga **solo-audio** (`bestaudio`) para transcripción, no el video completo por
  defecto.
- **Aprovechar subtítulos del creador** cuando existen (rápido, sin GPU); si no
  existen, caer al flujo de Whisper del motor local.
- Salidas idénticas al flujo local: texto plano, `.srt` con timestamps, audio.
- **Playlists en lote**: procesa todos los videos de la playlist en una corrida.
- Flags:
  - `--force-transcribe` — ignora subtítulos del creador y fuerza Whisper.
  - `--allow-auto-subs` — acepta subtítulos auto-generados (ASR de YouTube) como
    fuente en vez de caer a Whisper (prioriza velocidad sobre calidad).
  - `--lang <código>` — fuerza el idioma de subtítulos (default: automático).
  - `--keep-video` — conserva el archivo descargado en vez de borrarlo.
  - Selección de calidad de audio (nivel a definir en el plan; expuesto como flag).
- Verificación de `yt-dlp` como binario del sistema al inicio, con error claro si
  falta (invariante 5).
- Resumen final del lote: cuántos videos se lograron y cuáles fallaron, con la causa.

### NO incluye (fuera de alcance en V1)

- Integración con la GUI (fase posterior).
- Edición/recorte/recompresión del video (invariante 2).
- Cualquier transcripción en la nube (invariante 1).
- Descarga de video en alta calidad como salida entregable (solo `--keep-video` como
  utilidad; la salida entregable es texto + audio).
- Login/cookies para contenido que requiera cuenta (privado, de pago). V1 solo
  maneja contenido público; el contenido con login se reporta como fallo claro.
- Traducción automática y diarización (siguen sin decidirse en el proyecto).

## 5. Comportamiento Esperado

### 5.1 Un solo video

1. El usuario corre `tae url "https://..."`.
2. La herramienta verifica que `yt-dlp` esté disponible. Si no, aborta con un mensaje
   accionable antes de tocar la red.
3. Descarga el audio (`bestaudio`) y, si existen, los subtítulos del creador en el
   idioma resuelto (`--lang` o automático).
4. **Si hay subtítulos del creador y no se pasó `--force-transcribe`:** se usan esos
   subtítulos como fuente del texto/`.srt`. No se invoca Whisper.
5. **Si no hay subtítulos, o se pasó `--force-transcribe`:** se transcribe el audio
   con Whisper (motor local, GPU si hay, CPU si no).
6. Se generan las salidas (texto plano, `.srt`, audio) con el nombre derivado del
   título del video.
7. El archivo temporal descargado se borra, salvo `--keep-video`.
8. Al terminar, el usuario ve confirmación de qué se generó y dónde.

### 5.2 Playlist en lote

1. El usuario corre `tae url "<URL-de-playlist>"`.
2. La herramienta detecta que es una playlist y procesa **cada video en orden**.
3. Cada archivo de salida lleva un **prefijo numérico** que preserva el orden de la
   playlist (`01_`, `02_`, …).
4. Si dos videos comparten título, se desambigua con un **contador** (`_2`, `_3`).
5. Si un video falla (privado, geobloqueo, borrado, extractor roto), **se salta y el
   lote continúa** con el resto. Ningún fallo individual detiene la corrida.
6. Al terminar, el usuario ve un **resumen**: cuántos videos se procesaron con éxito,
   cuáles fallaron y por qué (una línea por fallo con su causa).

### 5.3 Nombres y salidas

- Nombre base = título del video saneado para sistema de archivos.
- Playlist: `NN_titulo` (prefijo de orden). Colisión de título: sufijo `_2`, `_3`.
- Las tres salidas (texto, `.srt`, audio) comparten el mismo nombre base con su
  extensión correspondiente, en el directorio de salida elegido.

## 6. Posibles Errores y Mitigaciones

| Situación | Qué ve/experimenta el usuario |
|---|---|
| **`yt-dlp` no está instalado** | Error claro al inicio ("`yt-dlp` no encontrado, instálalo/actualízalo"), antes de tocar la red. No traceback. |
| **`yt-dlp` desactualizado / extractor roto** | YouTube cambia seguido y rompe extractores. El fallo se reporta con un mensaje accionable que sugiere **actualizar `yt-dlp`**, no un stacktrace opaco. |
| **Video privado / requiere login** | Se reporta como fallo con causa "privado / requiere cuenta". En lote, se salta y continúa. V1 no maneja cookies/login. |
| **Video geobloqueado** | Fallo con causa "no disponible en tu región". En lote, se salta y continúa. |
| **Video borrado / URL inválida** | Fallo con causa "no disponible / URL inválida". En lote, se salta y continúa. |
| **Sin subtítulos del creador** | No es error: cae automáticamente a transcripción con Whisper. |
| **Subtítulos solo auto-generados (ASR de YouTube)** | Por defecto se **ignoran** (su calidad es pobre) y se cae a Whisper para tener texto consistente. Con `--allow-auto-subs` se aceptan como fuente, avisando al usuario que provienen de ASR y no del creador. Los subtítulos **oficiales del creador** siempre tienen prioridad sobre los ASR. |
| **Idioma pedido con `--lang` no disponible** | Aviso claro de que ese idioma no existe para el video; cae al idioma automático o a Whisper según el caso. |
| **Sin conexión de red** | Error claro de red; en lote, el resumen final refleja qué alcanzó a procesarse. |
| **Disco lleno durante descarga** | Error claro; se limpia el temporal parcial para no dejar basura. |
| **Sin GPU** | El motor degrada a CPU (más lento) sin crashear (invariante 3). |

### Nota sobre la invariante 1 (todo local)

`yt-dlp` toca la red **por diseño** — es la excepción explícita del scope online. La
red se usa **solo** para descargar la fuente (audio/subtítulos) desde la plataforma.
En ningún momento el audio o el video se envían a un tercero para ser transcritos: la
transcripción sigue siendo Whisper local. Esta frontera debe quedar visible en el
código y en la documentación del módulo.
