# TextAudioExtractor

App de Windows que extrae el **texto** y el **audio** de un video. Si el video trae
subtítulos incrustados, los extrae; si no, transcribe el audio con **Whisper local
(GPU)**. El texto se entrega en dos formatos: plano (`.txt`) y con marcas de tiempo
(`.srt`).

Motor headless reutilizable (`tae.core`) + GUI delgada en PySide6.

## Requisitos

- **Python ≥ 3.11** y [`uv`](https://docs.astral.sh/uv/).
- **ffmpeg** en el PATH (incluye `ffprobe`). Windows: `winget install Gyan.FFmpeg`.
- **yt-dlp** en el PATH (solo para el módulo online `tae url`). Es un binario del
  sistema, no una dependencia pip: así lo actualizas cuando una plataforma rompe un
  extractor sin esperar a un release de esta app.
  - Instalar/actualizar: `pip install -U yt-dlp` (o `winget install yt-dlp.yt-dlp`).
  - Si falta, solo el comando `tae url` avisa con un mensaje claro; el flujo local
    (`tae local`) funciona sin él.
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

Dos subcomandos: `local` (archivo de video) y `url` (YouTube/plataformas).

```bash
# Video local
uv run tae local "C:\ruta\video.mp4" --txt --srt --audio

# URL online (video o playlist)
uv run tae url "https://www.youtube.com/watch?v=..." --txt --srt --out .\salida
```

Opciones comunes:

| Flag | Qué hace |
|------|----------|
| `--txt` / `--no-txt` | Texto plano `.txt` (por defecto sí). |
| `--srt` / `--no-srt` | Subtítulos `.srt` con timestamps (por defecto sí). |
| `--audio` / `--no-audio` | Extraer el audio (por defecto no). |
| `--force-transcribe` | Transcribir aunque haya subtítulos disponibles. |
| `--lang es` | Fijar idioma. Por defecto autodetección (local) / idioma original (url). |
| `--model medium` | `tiny`/`base`/`small`/`medium`/`large-v3` (velocidad vs precisión). |
| `--out DIR` | Carpeta de salida. Local: `<carpeta del video>/<nombre>`. URL: carpeta actual. |
| `--audio-format mp3` | `mp3`/`m4a`/`wav`/`flac`. |
| `--diarize` | Identificar hablantes (ver sección abajo). Fuerza transcribir el audio. |
| `--speakers N` | Nº de hablantes si se conoce (ej. `2`). Por defecto, autodetección. |

Solo para `tae url`:

| Flag | Qué hace |
|------|----------|
| `--allow-auto-subs` | Aceptar subtítulos auto-generados (ASR) si el creador no puso. |
| `--keep-video` | Conservar la fuente descargada junto a las salidas. |

Si la URL es una **playlist**, se procesa en lote: cada video sale con prefijo
`NN_`, y al final se imprime un resumen con los éxitos y los fallos (con su causa:
privado, geobloqueo, borrado, etc.). Un video que falle no aborta el resto.

## Diarización de hablantes

Con `--diarize` (CLI) o el checkbox **"Identificar hablantes"** (GUI), la
transcripción separa **quién** habla: cada intervención sale prefijada con una
etiqueta genérica (`SPEAKER_00`, `SPEAKER_01`, …) en el `.srt` y el `.txt`. Útil
para sesiones 1-a-1 y entrevistas. Está **apagado por defecto**: sin el flag, la app
se comporta igual que siempre.

Como la identidad de voz sólo está en el audio, `--diarize` **transcribe el audio
aunque haya subtítulos** (los ignora y avisa). Todo corre local; el token de
HuggingFace de abajo sólo autoriza la **descarga inicial** de los modelos de
diarización — en runtime nada sale a la nube.

### Puesta a punto (una vez)

1. **Instala el extra** (arrastra torch y pyannote, es una descarga grande):

   ```bash
   uv sync --extra diarize
   ```

2. **Acepta los términos** del modelo de diarización de pyannote en HuggingFace
   (cuenta gratuita). Con las versiones actuales de whisperX el modelo por defecto es:
   - https://huggingface.co/pyannote/speaker-diarization-community-1

   Si tu versión usa otro modelo gated, la app te dice la **URL exacta** a aceptar en
   el mensaje de error (no un traceback).

3. **Crea un token** de acceso gratuito en
   https://huggingface.co/settings/tokens y expórtalo como variable de entorno:

   ```bash
   # PowerShell (Windows)
   $env:HF_TOKEN = "hf_xxxxxxxxxxxxxxxxxxxx"
   ```

   La app también acepta `HUGGINGFACE_TOKEN`.

Si falta el extra o el token, `--diarize` da un **mensaje claro** con estos pasos, no
un traceback. Sin GPU NVIDIA corre en CPU con aviso (es notablemente lento).

```bash
# Terapia de 2 voces, número de hablantes conocido
uv run tae local "sesion.mp4" --diarize --speakers 2
```

## Desarrollo

```bash
uv run pytest        # tests (los que necesitan media se saltan si falta ffmpeg)
uv run ruff check .  # lint
```

Estructura y decisiones en `CLAUDE.md`, `docs/specs/` y `docs/plans/`.

## Fuera de alcance (por ahora)

Edición de video, transcripción en la nube y traducción automática. (La diarización
de hablantes ya está soportada — ver sección arriba.)
