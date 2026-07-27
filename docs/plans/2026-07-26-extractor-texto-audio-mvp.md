# Plan de implementación — Extractor de texto y audio (MVP)

Fecha: 2026-07-26

## 1. Objetivo

Implementar el MVP: un motor headless en Python que, dado un video local, detecta
subtítulos incrustados y los extrae, o si no hay, transcribe el audio con
faster-whisper (GPU), y produce `.txt`, `.srt` y el audio separado — más una GUI
PySide6 delgada que llama a ese motor. Todo local, un video a la vez.

## 2. Contexto del problema

No existe una herramienta local, de un clic, que resuelva los dos casos (video con
o sin subtítulos) y entregue además el audio, sin mandar material propio a la nube.
Se construye motor reutilizable + GUI para uso interno de Kaiketek, con vistas a
producto. Detalle completo en el spec.

## 3. Spec de referencia

`docs/specs/2026-07-26-extractor-texto-audio-mvp.md` (aprobado 2026-07-26).

Decisiones cerradas que este plan asume: **faster-whisper**, **PySide6**, salida en
carpeta por defecto pero elegible antes de procesar, sin lotes, sin nube, sin
edición de video. Secciones del spec especialmente relevantes para el diseño
técnico: §5 (comportamiento del texto — `.txt` es el `.srt` sin marcas) y §6
(errores: falta ffmpeg, sin GPU degrada a CPU, sin pista de audio, subtítulos
dañados → fallback a transcripción, descarga de modelo, cancelación limpia).

## 4. Decisiones técnicas base

- **Estructura de segmentos unificada.** Tanto la extracción de subtítulos como la
  transcripción producen la misma lista de `Segment(start, end, text)`. De ahí se
  renderizan `.srt` (con marcas) y `.txt` (sin marcas). Esto cumple §5 del spec: una
  sola fuente para ambos formatos.
- **`ffmpeg`/`ffprobe` como binarios del sistema** (invariante 5). Se localizan y
  verifican al arranque; error claro si faltan.
- **Motor sin dependencia de la GUI** (invariante 4). `core` no importa nada de
  PySide6. La GUI corre el motor en un hilo aparte (`QThread`) y recibe progreso por
  señales.
- **Gestor de entorno:** `uv`. **Tests:** `pytest`. **Lint/format:** `ruff`.
- **Progreso de transcripción:** faster-whisper entrega segmentos en streaming; el
  progreso se estima como `segment.end / duración_total`.

## 5. Estructura de carpetas objetivo

```
TextAudioExtractor/
  pyproject.toml
  src/tae/
    core/
      __init__.py
      errors.py         # excepciones tipadas (FfmpegNotFound, NoAudioTrack, ...)
      ffmpeg_utils.py   # localizar/verificar ffmpeg y ffprobe
      probe.py          # ffprobe: duración, pistas de audio, pistas de subtítulos
      audio.py          # extraer audio a archivo
      subtitles.py      # extraer pista de subtítulos embebida -> Segment[]
      transcribe.py     # wrapper faster-whisper -> Segment[] (streaming)
      outputs.py        # Segment[] -> .srt y .txt
      pipeline.py       # orquestador: video + opciones -> resultados, con callbacks de progreso
      models.py         # dataclasses: Segment, ProbeResult, JobOptions, JobResult
    cli.py              # CLI (typer) -> pipeline
    gui/
      __init__.py
      app.py            # ventana principal PySide6
      worker.py         # QThread envolviendo pipeline, señales de progreso/estado
  tests/
    test_probe.py
    test_outputs.py
    test_pipeline.py
    fixtures/           # clips cortos de prueba (fuera de git si pesan)
```

## 6. Lista de tareas a implementar

### Bloque 0 — Andamiaje del proyecto Python

- **T1. Inicializar proyecto con `uv` y `pyproject.toml`.**
  - Archivos: `pyproject.toml`, `src/tae/__init__.py`.
  - Dependencias: `faster-whisper`, `pyside6`, `typer`. Dev: `pytest`, `ruff`.
  - Configurar layout `src/`, entry points de consola (`tae` → `tae.cli:app`) y GUI
    (`tae-gui` → `tae.gui.app:main`).
  - **Hecho cuando:** `uv sync` instala sin error y `uv run tae --help` responde
    (aunque el comando aún no haga nada).

- **T2. Definir modelos y errores.**
  - Archivos: `core/models.py`, `core/errors.py`.
  - `Segment(start: float, end: float, text: str)`; `ProbeResult` (duración, lista de
    pistas de audio, lista de pistas de subtítulos con idioma); `JobOptions` (qué
    salidas, forzar transcripción, idioma, modelo, carpeta de salida); `JobResult`
    (rutas generadas). Excepciones: `FfmpegNotFound`, `UnreadableVideo`,
    `NoAudioTrack`, `SubtitleExtractionFailed`, `OutputWriteError`.
  - **Hecho cuando:** los tipos importan y se usan en las firmas de las tareas
    siguientes.

### Bloque 1 — Motor (core)

- **T3. Localización y verificación de ffmpeg/ffprobe.**
  - Archivo: `core/ffmpeg_utils.py`.
  - Buscar `ffmpeg`/`ffprobe` en PATH; función `ensure_ffmpeg()` que lanza
    `FfmpegNotFound` con mensaje accionable si faltan.
  - **Hecho cuando:** en un sistema sin ffmpeg lanza el error claro; con ffmpeg
    devuelve las rutas. Cubierto por test que mockea el PATH.

- **T4. Probe del video.**
  - Archivo: `core/probe.py`. Usa `ffprobe -show_streams` (JSON).
  - Devuelve `ProbeResult`: duración, ¿hay pista de audio?, lista de pistas de
    subtítulos con su idioma. Lanza `UnreadableVideo` si ffprobe falla.
  - **Hecho cuando:** con un clip con subs devuelve las pistas; con uno sin audio
    marca `has_audio=False`; con un archivo corrupto lanza `UnreadableVideo`.

- **T5. Extracción de audio.**
  - Archivo: `core/audio.py`.
  - `extract_audio(video, out_path)` vía ffmpeg. Formato de audio configurable
    (default un contenedor común; para Whisper internamente se usará 16kHz mono wav).
    Si no hay pista de audio, lanza `NoAudioTrack`.
  - **Hecho cuando:** genera el archivo de audio esperado y lanza `NoAudioTrack` en
    video mudo.

- **T6. Extracción de subtítulos incrustados.**
  - Archivo: `core/subtitles.py`.
  - `extract_subtitles(video, track_index) -> Segment[]`: ffmpeg extrae la pista a
    `.srt` temporal y se parsea a `Segment[]`. Si falla, lanza
    `SubtitleExtractionFailed` (el pipeline decidirá el fallback).
  - **Hecho cuando:** de un clip con subs devuelve segmentos con tiempos y texto
    correctos; ante pista dañada lanza la excepción.

- **T7. Transcripción con faster-whisper.**
  - Archivo: `core/transcribe.py`.
  - `transcribe(audio, model, language, on_progress) -> Segment[]`. Carga el modelo
    (auto GPU si hay CUDA, si no CPU con aviso vía callback — invariante 3). Itera
    los segmentos en streaming y llama `on_progress(fraction)` con
    `segment.end / duración`. `language=None` = autodetección.
  - **Hecho cuando:** transcribe un clip corto en GPU, devuelve segmentos con
    timestamps, reporta progreso, y en máquina sin GPU corre en CPU sin crashear.

- **T8. Render de salidas.**
  - Archivo: `core/outputs.py`.
  - `write_srt(segments, path)` (bloques numerados, `HH:MM:SS,mmm`), `write_txt(
    segments, path)` (párrafos legibles, sin marcas). Lanza `OutputWriteError` ante
    fallo de disco/permiso.
  - **Hecho cuando:** un `Segment[]` fijo produce un `.srt` válido y un `.txt` que es
    el mismo contenido sin marcas. Cubierto por test de snapshot.

- **T9. Orquestador (pipeline).**
  - Archivo: `core/pipeline.py`.
  - `run(video, options, on_progress, on_stage, cancel_token) -> JobResult`. Lógica:
    `ensure_ffmpeg` → `probe` → decidir ruta (extraer subs si existen y no se fuerza
    transcripción; si la extracción falla → fallback a transcripción, §6 spec) →
    generar salidas pedidas (audio, `.txt`, `.srt`) en la carpeta elegida →
    `JobResult`. Emite etapas ("Extrayendo audio…", "Transcribiendo…") por
    `on_stage`. Respeta `cancel_token` entre etapas y descarta parciales al cancelar.
  - **Hecho cuando:** para un video con subs genera salidas sin transcribir; para uno
    sin subs transcribe; forzar-transcripción ignora la pista; cancelar deja sin
    archivos válidos. Cubierto por `test_pipeline.py`.

### Bloque 2 — CLI

- **T10. Comando CLI sobre el pipeline.**
  - Archivo: `cli.py` (typer).
  - `tae <video> [--txt] [--srt] [--audio] [--force-transcribe] [--lang xx]
    [--model small|medium|large] [--out DIR]`. Imprime progreso y etapas en consola,
    y la ruta de resultados al final. Errores del motor se muestran como mensajes
    claros, no tracebacks.
  - **Hecho cuando:** `uv run tae clip.mp4 --srt --txt --audio` produce los tres
    archivos; flags de idioma/modelo/salida funcionan; un video inexistente da error
    legible.

### Bloque 3 — GUI (PySide6, cliente delgado)

- **T11. Worker en hilo.**
  - Archivo: `gui/worker.py`.
  - `QThread`/worker que ejecuta `pipeline.run` y reemite `on_progress`/`on_stage`
    como señales Qt; señal de cancelación conectada al `cancel_token`.
  - **Hecho cuando:** la GUI puede correr un job sin congelarse y recibir progreso.

- **T12. Ventana principal.**
  - Archivo: `gui/app.py`.
  - Zona de arrastrar/elegir video; al cargar muestra nombre, duración y subtítulos
    detectados (§5 spec, pasos 1-2). Casillas de salida (`.txt`/`.srt`/audio);
    selector de carpeta de salida con default y botón "cambiar" **antes** de procesar
    (paso 4); controles de idioma y modelo (visibles/relevantes cuando habrá
    transcripción); casilla "transcribir de todos modos". Botón Iniciar → barra de
    progreso con etapa en texto. Al terminar, resumen + botón "abrir carpeta".
  - **Hecho cuando:** el flujo completo del §5 del spec corre desde la ventana para un
    video con subs y para uno sin subs, con la carpeta de salida elegida respetada.

- **T13. Manejo de errores en la GUI.**
  - Archivo: `gui/app.py`.
  - Mapear cada excepción del motor a un diálogo claro (falta ffmpeg y bloquea inicio;
    sin GPU → aviso no bloqueante; video corrupto; sin audio; subs dañados con oferta
    de transcribir; disco/permiso; "Descargando modelo…"). Cubre §6 del spec.
  - **Hecho cuando:** cada caso de §6 muestra el mensaje correcto en vez de un
    traceback.

### Bloque 4 — Verificación y cierre (no romper lo definido)

- **T14. Tests del motor y chequeo de invariantes.**
  - Archivos: `tests/`.
  - Tests de `probe`, `outputs`, `pipeline` (con clips-fixture cortos). Verificar
    explícitamente: motor no importa PySide6 (invariante 4); sin GPU no crashea
    (invariante 3); sin ffmpeg da error claro (invariante 5).
  - **Hecho cuando:** `uv run pytest` pasa en verde y las tres verificaciones de
    invariantes tienen su test.

- **T15. README de uso mínimo.**
  - Archivo: `README.md`.
  - Requisitos (ffmpeg, GPU opcional), cómo instalar con `uv`, cómo correr CLI y GUI.
  - **Hecho cuando:** siguiendo el README desde cero se instala y corre.

## 7. Fuera de este plan (coherente con el spec)

YouTube/`yt-dlp`, traducción, diarización, procesamiento por lotes, empaquetado a
`.exe` distribuible. Se retoman en fases posteriores; la estructura del motor deja
lugar para enchufar la descarga online como una fuente de entrada más.

## 8. Orden sugerido de ejecución

T1 → T2 → T3 → T4 → (T5, T6, T7 en paralelo posible) → T8 → T9 → T10 → T11 → T12 →
T13 → T14 → T15.
