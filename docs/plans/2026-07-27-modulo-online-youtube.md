# Plan de Implementación — Módulo Online (YouTube/plataformas) · Fase 4

- **Fecha:** 2026-07-27
- **Spec de referencia:** `docs/specs/2026-07-27-modulo-online-youtube.md` (aprobado)

## Objetivo

Añadir un paquete aislado `src/tae/online/` que, dada una URL de YouTube u otra
plataforma soportada por `yt-dlp`, descargue la fuente (solo-audio + subtítulos del
creador), reutilice las primitivas del motor (`transcribe`, `outputs`, `audio`) y
entregue texto plano, `.srt` y audio. Se expone como el comando `tae url <URL>` y
soporta playlists en lote.

## Contexto del Problema

Hoy `tae` solo procesa videos locales. Sacar texto/audio de un video de YouTube
obliga a descargarlo a mano primero, y desperdicia GPU transcribiendo cuando el
creador ya subió subtítulos. El módulo online elimina el paso manual, aprovecha
subtítulos existentes y escala a playlists desatendidas. Ver spec §3.

## Spec de Referencia y decisiones que condicionan el diseño

Archivo: `docs/specs/2026-07-27-modulo-online-youtube.md`. Secciones que dirigen
decisiones técnicas:

- **§5.1 / §5.2** — flujo un-video vs playlist; numeración `NN_`, contador de
  colisión, seguir-y-reportar en fallos.
- **§6** — errores por causa (privado/geobloqueo/borrado/yt-dlp desactualizado) con
  mensajes accionables; ASR por defecto se ignora (`--allow-auto-subs` lo acepta).
- **Invariante 1** — la red es solo para traer la fuente; la transcripción sigue
  siendo Whisper local.

### Principios de diseño (cómo encaja con el motor actual)

- **Capa aislada:** toda la orquestación online vive en `src/tae/online/`. El core
  no se acopla al módulo online (invariante 4).
- **Cambios al core solo aditivos:** se agrega un parser de `.vtt` a
  `core/subtitles.py` (los subs de YouTube vienen en WebVTT). No se modifica ninguna
  firma existente.
- **`yt-dlp` como binario del sistema:** se verifica al inicio con el mismo patrón
  que `ffmpeg_utils.ensure_ffmpeg` (invariante 5). *(Decisión abierta menor — ver
  Tarea 1: verificar binario vs. declararlo dependencia pip.)*
- **Reutilización de `Segment`:** subtítulos descargados y transcripción producen la
  misma `list[Segment]`; de ahí salen `.srt` y `.txt` con `core.outputs`, sin
  duplicar código.

## Lista de Tareas a Implementar

### Bloque A — Fundaciones del módulo

**A1. Verificación de `yt-dlp` (`src/tae/online/ytdlp_utils.py`)**
- Espejo de `core/ffmpeg_utils.py`: `find_ytdlp()`, `ensure_ytdlp()` (lanza error si
  falta), y un `run()` que oculta la consola en Windows (`CREATE_NO_WINDOW`).
- `ensure_ytdlp()` incluye un hint de instalación/actualización accionable
  (`pip install -U yt-dlp` / winget), cubriendo §6 "yt-dlp ausente/desactualizado".
- **Archivos:** nuevo `src/tae/online/__init__.py`, `src/tae/online/ytdlp_utils.py`.
- **Decisión abierta:** ¿verificar binario del sistema (recomendado, consistente con
  ffmpeg) o añadir `yt-dlp` a `dependencies` en `pyproject.toml`? Recomiendo binario
  del sistema para mantener el patrón. Confirmar con Kike antes de cerrar.
- **Hecho cuando:** `ensure_ytdlp()` devuelve la ruta si está y lanza un error tipado
  con mensaje claro si no; test unitario que fuerza el caso "no está".

**A2. Errores tipados del módulo (`src/tae/online/errors.py`)**
- Subclases de `core.errors.TaeError` (para que CLI/GUI las muestren igual):
  `YtDlpNotFound`, `DownloadFailed`, y un enum/campo de **causa**
  (`PRIVATE`, `GEOBLOCKED`, `UNAVAILABLE`, `NEEDS_LOGIN`, `EXTRACTOR_ERROR`,
  `NETWORK`, `UNKNOWN`) para poder clasificar fallos y armar el resumen del lote.
- **Archivos:** nuevo `src/tae/online/errors.py`.
- **Hecho cuando:** cada causa mapea a un mensaje accionable en español (§6); las
  clases heredan de `TaeError`.

### Bloque B — Descarga y parseo

**B1. Parser de WebVTT en el core (`src/tae/core/subtitles.py`)**
- Añadir `parse_vtt(content: str) -> list[Segment]` (aditivo). WebVTT es casi SRT
  pero con cabecera `WEBVTT`, milisegundos con `.`, y posibles *cue settings* y tags
  inline (`<c>`, `<00:00:01.000>`) que hay que limpiar. Reutiliza `_to_seconds`.
- Alternativa considerada y descartada: convertir vtt→srt con ffmpeg (añade un salto
  de proceso y ya tenemos el parser SRT tolerante a mano).
- **Archivos:** `src/tae/core/subtitles.py` (solo se agrega función).
- **Hecho cuando:** `test_subtitles_parse.py` cubre un `.vtt` real (con header y tags
  inline) y produce los `Segment` correctos; el parser SRT existente sigue intacto.

**B2. Descarga vía yt-dlp (`src/tae/online/download.py`)**
- `download(url, work_dir, *, lang, allow_auto_subs, keep_video) -> DownloadResult`.
- Usa `yt-dlp` para bajar `bestaudio` + subtítulos (`--write-subs`, y
  `--write-auto-subs` solo si `allow_auto_subs`) al `work_dir`, con `--sub-langs`
  según `--lang` (o el idioma original si `lang is None`).
- Extrae metadatos con `--print`/`--dump-json` (o `%(...)s` en `-o`) para obtener
  título, id, idioma y si el subtítulo es del creador vs auto-generado.
- Prioriza subtítulos **oficiales del creador**; los auto-generados solo se
  consideran si `allow_auto_subs` (spec §6, ASR).
- Clasifica fallos de yt-dlp a las causas de A2 parseando su stderr (privado,
  geobloqueo, borrado, login, extractor).
- Devuelve `DownloadResult` (dataclass): `audio_path`, `subtitle_path | None`,
  `subtitle_is_auto: bool`, `title`, `language`, y para playlists el `index` y
  `playlist_title`.
- **Archivos:** nuevo `src/tae/online/download.py`; `DownloadResult` en
  `src/tae/online/models.py` (o dentro de download.py si es pequeño).
- **Hecho cuando:** con la red mockeada (subprocess simulado), un video con subs y
  otro sin subs producen el `DownloadResult` esperado; un fallo simulado de yt-dlp se
  traduce a la causa correcta.

**B3. Listado/expansión de playlist (`src/tae/online/download.py`)**
- `probe_url(url) -> UrlInfo`: detecta si la URL es un video único o una playlist y,
  si es playlist, devuelve la lista ordenada de entradas (id/título) usando
  `yt-dlp --flat-playlist --dump-json`.
- **Hecho cuando:** una URL de playlist mockeada devuelve N entradas en orden; una URL
  de video único devuelve una sola entrada.

### Bloque C — Orquestación online

**C1. Runner de un solo video (`src/tae/online/runner.py`)**
- `run_url(opts: OnlineJobOptions, callbacks...) -> OnlineJobResult`.
- Flujo (espeja `pipeline._obtain_text` pero sobre artefactos descargados):
  1. `ensure_ytdlp()` + `ensure_ffmpeg()`.
  2. `download(...)`.
  3. Si hay subtítulo válido del creador (o auto permitido) y no `force_transcribe`:
     parsear con `parse_vtt` → `Segment[]`, fuente `EMBEDDED`.
  4. Si no: transcribir el audio descargado con `core.transcribe.transcribe`, fuente
     `TRANSCRIBED`.
  5. Escribir `.srt`/`.txt` con `core.outputs`; entregar el audio en el formato pedido
     (reusar `core.audio` para transcodificar `bestaudio` → mp3/etc.).
  6. Borrar temporales salvo `keep_video`.
- `OnlineJobOptions` reutiliza los campos de `JobOptions` que apliquen
  (want_txt/srt/audio, force_transcribe, language, model, audio_format, out_dir) más
  `url`, `allow_auto_subs`, `keep_video`. Evaluar componer sobre `JobOptions` para no
  duplicar.
- **Archivos:** nuevo `src/tae/online/runner.py`, `src/tae/online/models.py`.
- **Hecho cuando:** con descarga y transcripción mockeadas, los tres caminos
  (subs creador / sin subs→whisper / force_transcribe) generan las salidas correctas
  y respetan `keep_video`.

**C2. Runner de lote/playlist (`src/tae/online/runner.py`)**
- `run_playlist(...)`: expande la playlist (B3), procesa cada entrada con `run_url`,
  y **captura los fallos por entrada** sin abortar el lote (spec §5.2, §6).
- Nombres de salida: prefijo `NN_` según orden de playlist; ante colisión de título,
  sufijo `_2`, `_3` (helper de nombres reutilizable, ver C3).
- Devuelve un `BatchReport`: lista de éxitos (rutas) y de fallos
  (título/url + causa legible).
- **Hecho cuando:** un lote mockeado con 1 fallo intermedio procesa el resto y el
  `BatchReport` refleja 1 fallo con su causa + N éxitos.

**C3. Helper de nombres de salida (`src/tae/online/naming.py`)**
- `safe_stem(title)` (sanea para filesystem) y `resolve_collisions(stem, used_set)`
  (aplica `_2/_3`), y `numbered(index, stem)` (`01_...`).
- **Archivos:** nuevo `src/tae/online/naming.py`.
- **Hecho cuando:** tests cubren saneo de caracteres inválidos, colisión y numeración.

### Bloque D — CLI

**D1. Comando `tae url` (`src/tae/cli.py`)**
- Añadir el subcomando `url` con: `URL` (arg), `--txt/--srt/--audio`,
  `--force-transcribe`, `--allow-auto-subs`, `--lang`, `--model`, `--out`,
  `--audio-format`, `--keep-video`.
- Detecta video único vs playlist (`probe_url`) y despacha a `run_url` /
  `run_playlist`. Reusa los callbacks de consola (`on_stage/on_info/on_progress`) ya
  existentes.
- Para lote, imprime el **resumen final** (éxitos/fallos con causa) al terminar.
- **Decisión de estructura de CLI (requiere confirmación):** hoy `tae <video>` es el
  único comando (`@app.command()` sin nombre). Para agregar `tae url` hay que pasar a
  multi-comando. Propuesta: `tae local <video>` (el flujo actual, renombrado) + `tae
  url <URL>`. Esto **rompe** la invocación `tae <video>` directa. Alternativa: mantener
  el flujo local como comando por defecto vía callback `invoke_without_command`.
  Recomiendo `local` + `url` explícitos por claridad; confirmar con Kike.
- **Archivos:** `src/tae/cli.py`.
- **Hecho cuando:** `tae url <URL>` corre el flujo online end-to-end (con red real en
  prueba manual); `tae local <video>` sigue funcionando igual que antes; errores
  `TaeError` se muestran sin traceback.

### Bloque E — Dependencias, tests y no romper lo existente

**E1. Dependencias (`pyproject.toml`)**
- Según la decisión de A1: si se declara `yt-dlp` como dependencia pip, agregarlo a
  `dependencies`. Si se deja como binario del sistema, documentarlo en el README
  junto a ffmpeg. (Recomendación: binario del sistema.)
- **Hecho cuando:** `uv sync` funciona; la ausencia de yt-dlp da error claro, no
  crash.

**E2. Tests del módulo online (`tests/`)**
- `test_vtt_parse.py` — parseo de WebVTT (B1).
- `test_online_naming.py` — numeración y colisiones (C3).
- `test_online_batch.py` — resumen de lote con fallos mockeados (C2).
- `test_online_download.py` — clasificación de causas de fallo de yt-dlp con stderr
  simulado (B2), sin tocar la red.
- Todos sin acceso a red (mock de subprocess/yt-dlp), consistente con el estilo actual
  de `tests/`.
- **Hecho cuando:** `pytest` pasa (los 17 actuales + los nuevos) y `ruff` queda limpio.

**E3. No romper el motor ni la CLI existentes (verificación explícita)**
- Confirmar que `core/subtitles.py` sigue exportando `extract_subtitles`/`parse_srt`
  intactos y que `pipeline.run` no cambió.
- Confirmar que el flujo local (`tae local <video>` o el default elegido) produce las
  mismas salidas que antes de esta fase.
- **Hecho cuando:** los tests existentes (`test_pipeline_media`, `test_outputs`,
  `test_subtitles_parse`, `test_invariants`) pasan sin modificación.

## Verificación posterior

Al implementar, usar `k-verify-after-changes` contra este plan y el spec. Casos clave
a probar (derivados de §5–§6): (1) URL con subs del creador → texto sin Whisper;
(2) URL sin subs → cae a Whisper; (3) `--force-transcribe`; (4) playlist con un video
privado → resto procesado + resumen con la causa; (5) `yt-dlp` ausente → error claro.
Prueba manual con red real requerida para al menos los casos 1, 2 y 4.
