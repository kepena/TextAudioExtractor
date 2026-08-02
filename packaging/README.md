# Empaquetado de TextAudioExtractor (Windows, carpeta portable)

Ver spec/plan: `docs/specs/2026-08-01-empaquetado-windows-portable.md`,
`docs/plans/2026-08-01-empaquetado-windows-portable.md`.

## Cómo se construye

Un solo comando, desde la raíz del repo:

```powershell
./packaging/build_windows.ps1
```

Internamente corre `uv run --extra diarize pyinstaller packaging/tae-gui.spec`
(el `--extra diarize` es obligatorio: sin él, `whisperx`/`torch` no están en el
venv de build y la diarización CPU no queda bundleada — ver P10 en
`docs/pendientes.md`), copia los binarios externos y deja `dist/tae-gui/`
listo para mover a cualquier carpeta.

**El venv de build vive en disco local** (`C:\Users\kepen\.venvs\tae\`), no
como `.venv` dentro de este repo — el repo está en `G:` (unidad de red) y un
venv con torch/whisperx ahí revienta con error de Windows (ver P13 en
`docs/pendientes.md`). `build_windows.ps1` fija esto internamente
(`$env:UV_PROJECT_ENVIRONMENT`); no requiere nada manual.

**El build de PyInstaller también corre en disco local**
(`%LOCALAPPDATA%\TextAudioExtractor\build` y `...\dist`), por la misma razón:
G: (Google Shared Drive) compite con PyInstaller por los mismos archivos
durante el `COLLECT` (~40 min, cientos de miles de archivos chicos) y da
"acceso denegado"/recursos insuficientes a mitad de camino (visto en la
práctica). El resultado final se copia a `dist/tae-gui` de este repo en un
solo paso al terminar, y también queda disponible directamente en
`%LOCALAPPDATA%\TextAudioExtractor\dist\tae-gui` sin pasar por G: en absoluto.

## Binarios externos (no son pip, hay que colocarlos a mano)

Estos binarios **no se descargan automáticamente** — es un paso manual porque
descargar y ejecutar binarios de terceros requiere confirmación explícita.
Colocarlos en `packaging/bin/` (el script de build los copia de ahí a
`dist/tae-gui/`):

- **`ffmpeg.exe` / `ffprobe.exe`** — build oficial de Windows de
  <https://www.gyan.dev/ffmpeg/builds/> (el mismo que recomienda el hint de
  error de la app, `winget install Gyan.FFmpeg` — ver
  `src/tae/core/errors.py`), variante "essentials", extraídos de la carpeta
  `bin/` del zip `ffmpeg-release-essentials.zip`.
  Versión colocada el 2026-08-01: **ffmpeg 8.1.2-essentials_build**.
- **`yt-dlp.exe`** — release oficial standalone de
  <https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe>.
  Versión colocada el 2026-08-01: **2026.07.04**. **yt-dlp cambia seguido**
  por el anti-bot de YouTube (ver P5/P8 en `docs/pendientes.md`) — hay que
  repetir esta descarga cada vez que se reconstruya el paquete si se sospecha
  que quedó desactualizado.

## DLL de CUDA

El script de build copia los `.dll` de `nvidia-cublas-cu12`/`nvidia-cudnn-cu12`
desde el `site-packages` del venv de build (`.venv/Lib/site-packages/nvidia/`)
a `dist/tae-gui/cuda_dlls/`. No requiere descarga aparte — ya están instalados
como dependencia pip del proyecto (ver `pyproject.toml`).

## Fuera de alcance (ver spec)

- No se automatiza el setup de WSL2/GPU para diarización — sigue siendo
  `scripts/wsl_diarize_setup.sh`, manual.
- No se bundlean los pesos de Whisper/pyannote — se descargan en el primer
  uso, como en `uv run`.
- No se empaqueta el CLI (`tae.exe`) — solo la GUI.
