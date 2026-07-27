# TextAudioExtractor

App de Windows que extrae el **texto** y el **audio** de un video. Si el video trae
subtítulos incrustados, los extrae; si no, transcribe el audio con **Whisper local
(GPU)**. El texto se entrega en dos formatos: plano (`.txt`) y con marcas de tiempo
(`.srt`).

Motor headless reutilizable (`tae.core`) + GUI delgada en PySide6.

## Requisitos

- **Python ≥ 3.11** y [`uv`](https://docs.astral.sh/uv/).
- **ffmpeg** en el PATH (incluye `ffprobe`). Windows: `winget install Gyan.FFmpeg`.
- **GPU NVIDIA (opcional pero recomendada).** Con GPU la transcripción va mucho más
  rápido; sin ella corre en CPU (más lento), no falla.

## Instalación

```bash
uv sync
```

Esto instala el motor, la GUI y —en Windows— las librerías CUDA (`nvidia-cublas-cu12`,
`nvidia-cudnn-cu12`) para que la transcripción use la GPU.

## Uso

### GUI

```bash
uv run tae-gui
```

Arrastra un video, elige qué generar (`.txt`, `.srt`, audio), ajusta la carpeta de
salida si quieres, y pulsa Iniciar.

### Línea de comandos

```bash
uv run tae "C:\ruta\video.mp4" --txt --srt --audio
```

Opciones:

| Flag | Qué hace |
|------|----------|
| `--txt` / `--no-txt` | Texto plano `.txt` (por defecto sí). |
| `--srt` / `--no-srt` | Subtítulos `.srt` con timestamps (por defecto sí). |
| `--audio` / `--no-audio` | Extraer el audio (por defecto no). |
| `--force-transcribe` | Transcribir aunque el video traiga subtítulos incrustados. |
| `--lang es` | Fijar idioma. Por defecto autodetección. |
| `--model medium` | `tiny`/`base`/`small`/`medium`/`large-v3` (velocidad vs precisión). |
| `--out DIR` | Carpeta de salida. Por defecto `<carpeta del video>/<nombre>`. |
| `--audio-format mp3` | `mp3`/`m4a`/`wav`/`flac`. |

## Desarrollo

```bash
uv run pytest        # tests (los que necesitan media se saltan si falta ffmpeg)
uv run ruff check .  # lint
```

Estructura y decisiones en `CLAUDE.md`, `docs/specs/` y `docs/plans/`.

## Fuera de alcance (por ahora)

Edición de video, transcripción en la nube, YouTube/plataformas online, traducción,
diarización de hablantes y procesamiento por lotes.
