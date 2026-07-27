# CLAUDE.md — TextAudioExtractor

App de Windows que, dado un video, extrae su **texto** (subtítulos incrustados si
existen; si no, transcripción del audio con Whisper local en GPU) y su **audio**.
El texto se entrega en dos formas: plano y con marcas de tiempo tipo `.srt`.
Uso interno de Kaiketek al arranque, diseñado para poder volverse producto después.

**El proceso de trabajo y mi estilo viven en el CLAUDE.md global (`~/.claude`).
Aquí va solo lo de este repo.**

## Qué es

Arquitectura del **camino 3**: un motor headless reutilizable con una GUI delgada
encima.

```
video (local | YouTube/online)
        │
        ▼
  ┌─────────────┐   ¿trae subtítulos incrustados?
  │  detección  │──── sí ──► extraer pista (ffmpeg)
  └─────────────┘
        │ no
        ▼
  extraer audio (ffmpeg) ──► transcribir (Whisper local, GPU) ──► .srt
        │
        ▼
  salidas: texto plano · .srt con timestamps · audio separado
```

- **Motor (`core`):** librería/CLI en Python. Sin dependencia de la GUI. Es lo
  reutilizable el día que esto sea producto o servicio.
- **GUI:** cliente delgado encima del motor. Framework por decidir en el spec.
- **Módulo online (`yt-dlp`):** capa aislada y opcional para YouTube/plataformas.
  No reutiliza la app de descargas anterior (decisión de Kike).

## Stack

- **Lenguaje:** Python.
- **Binarios externos (dependencias duras, no son pip):**
  - `ffmpeg` — extrae audio y pistas de subtítulos embebidas.
  - `whisper` (openai-whisper / faster-whisper, por decidir en spec) — transcripción
    local. **Requiere GPU NVIDIA** para tiempos usables; solo CPU es 3-5x el
    tiempo del video.
  - `yt-dlp` — descarga de YouTube/online (módulo opcional).
- **Gestor de entorno / tests / lint:** por definir en el spec.

## Mapa de archivos

- `src/tae/core/` — motor headless (sin GUI): `models`, `errors`, `ffmpeg_utils`,
  `probe`, `audio`, `subtitles`, `transcribe`, `outputs`, `pipeline`.
- `src/tae/cli.py` — CLI typer (`tae`).
- `src/tae/gui/` — GUI PySide6: `app` (ventana) + `worker` (QThread).
- `tests/` — pytest (salidas, parseo SRT, invariantes, integración con media).
- `pyproject.toml` — deps y config (uv, ruff, pytest).
- `docs/` — proceso vivo (ver abajo).

## Invariantes y trampas de este proyecto

1. **Todo local, nada a la nube.** El MVP no sube audio ni video a ningún tercero.
   Cualquier PR que meta una API de transcripción en la nube rompe una decisión de
   alcance explícita — no hacerlo sin aprobación de Kike.
2. **No se edita el video.** El scope es extraer texto y audio; nada de cortar,
   recomprimir ni re-codificar el video original.
3. **GPU es supuesto de rendimiento, no requisito de arranque.** El motor debe
   funcionar en CPU (aunque lento) y no crashear si no hay GPU: degradar, avisar,
   no morir.
4. **El motor no depende de la GUI.** `core` tiene que poder correr y probarse solo
   (CLI/tests) sin importar nada de la interfaz. Si un cambio acopla motor y GUI,
   está mal.
5. **`ffmpeg`/`whisper`/`yt-dlp` son binarios del sistema.** Verificar su presencia
   y dar un error claro si faltan, en vez de reventar con un traceback.

## Alcance — fuera por ahora

- Edición de video (invariante 2).
- Transcripción en la nube (invariante 1).
- *Por decidir en el spec, no descartado:* traducción automática y diarización de
  hablantes (Kike no los excluyó explícitamente).

## Estado actual

- ✅ MVP implementado y verificado (2026-07-26): motor + CLI + GUI. `pytest` 17/17,
  `ruff` limpio, transcripción end-to-end en GPU (RTX 4050, CUDA/float16).
- ⏳ Falta prueba manual de la GUI con un video de voz real (P4) y el módulo
  YouTube/online (P5, fase posterior).

## Flujo y verificación

Sigue el flujo del global (brainstorm → spec → plan → implementar → verificar) con
los skills `k-*`. Brainstorm ya hecho: camino 3, Whisper local con GPU NVIDIA,
empezar interno. Aquí "verificar" arrancará por el comando de tests del motor una
vez definido el stack en el spec.
