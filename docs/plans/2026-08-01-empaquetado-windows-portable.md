# Plan — Empaquetado de TextAudioExtractor como carpeta portable de Windows

## Objetivo

Producir una carpeta portable de Windows (PyInstaller `--onedir`) con
`tae-gui.exe` que Kike pueda arrancar con doble clic, sin terminal ni Python
instalado, con `ffmpeg`/`yt-dlp` y la diarización CPU (whisperx) bundleados, y
un script de build que reconstruye todo con un solo comando.

## Contexto del Problema

Hoy la GUI solo arranca con `uv run tae-gui`, lo que exige tener el venv del
proyecto activo. Es fricción para el uso interno diario de Kike, que quiere
un ejecutable normal de Windows.

## Spec de Referencia

`docs/specs/2026-08-01-empaquetado-windows-portable.md`

Puntos del spec especialmente relevantes para las tareas técnicas:

- Alcance v1: solo GUI (no CLI), carpeta portable (no instalador), WSL2/GPU
  sin tocar (cae a CPU si no está), diarización CPU bundleada, modelos que
  se descargan en primer uso.
- "Posibles Errores": smoke test antes de dar el build por bueno, rutas con
  espacios (`G:\Unidades compartidas\...`), `ffmpeg`/`yt-dlp` faltantes deben
  seguir dando el mismo error claro que hoy (invariante 5).

## Hallazgos del código actual (base para las tareas)

- `find_ffmpeg()`/`find_ytdlp()` (`src/tae/core/ffmpeg_utils.py:28-47`,
  `src/tae/online/ytdlp_utils.py:45-47`) usan **solo `shutil.which` sobre
  PATH** — no hay config de ruta custom.
- Assets/fuentes de la GUI se resuelven con `Path(__file__).parent / "assets"`
  y `.../fonts` (`src/tae/gui/app.py:73,78,656`) — funcionan igual en
  PyInstaller onedir *si* el `.spec` declara esas carpetas como `datas`.
- `_add_cuda_dll_dirs` (`src/tae/core/transcribe.py:21-46`) localiza los DLL
  de `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` vía `site.getsitepackages()` —
  **no funciona en un exe congelado** (no hay site-packages real ahí).
- `diarize_wsl.py:55-56` calcula `_REPO_ROOT = Path(__file__).resolve().parents[3]`
  para localizar `scripts/wsl_diarize_worker.py` **fuera** del paquete `tae` —
  **se rompe en PyInstaller** (no existe ese árbol de carpetas en el build).
- El subproceso del motor (P12) usa `multiprocessing.Process` con `spawn`
  (`src/tae/gui/worker.py:58-65`), y `app.py:669-673` ya llama
  `freeze_support()` — esto es justo el mecanismo que un exe PyInstaller
  necesita para no relanzar la GUI completa en el hijo; **hay que verificarlo
  en el build real, no debería requerir cambio de código**.
- Diarización CPU (whisperx) tiene import diferido en
  `src/tae/core/diarize.py:140-143` — solo se importa si `--diarize` se usa,
  lo que ayuda a que PyInstaller no necesite resolverlo salvo que se fuerce
  su inclusión explícita (hidden imports/`collect_all`).

## Lista de Tareas a Implementar

### Bloque A — Entorno y layout de build

**A1. Crear carpeta `packaging/` para todo lo de este empaquetado**
Nueva carpeta top-level `packaging/` (separada de `scripts/`, que ya es de
WSL2/diarización) con: el `.spec` de PyInstaller, el script de build, y un
`README.md` corto con el procedimiento manual de descarga de binarios.
Criterio: carpeta creada, referenciada por el resto de tareas.

**A2. Añadir PyInstaller como dependencia de build**
Agregar `pyinstaller` a `[dependency-groups] dev` en `pyproject.toml`.
Criterio: `uv sync` instala PyInstaller sin conflictos de versión.

**A3. Documentar el requisito de construir con el extra `diarize` activo**
El build debe correr con `uv run --extra diarize pyinstaller ...` (no
`uv run` a secas), porque el spec decidió bundlear whisperx/torch CPU como
fallback de diarización. Documentarlo en `packaging/README.md`.
Criterio: el comando de build documentado incluye `--extra diarize`.

### Bloque B — Fixes de código para compatibilidad con PyInstaller

**B1. Inyectar la carpeta del ejecutable al PATH al arrancar**
En el entry point de la GUI (`src/tae/gui/app.py`, inicio de `main()`, antes
de cualquier otra cosa), si `sys.frozen` es `True`, anteponer la carpeta del
propio ejecutable (`Path(sys.executable).parent`) a `os.environ["PATH"]`.
Así `find_ffmpeg()`/`find_ytdlp()` (que no cambian) encuentran los binarios
bundleados sin tocar su lógica de detección, y el subproceso del motor
(`multiprocessing.Process`, que hereda el entorno del padre) también los ve.
Criterio: con `ffmpeg.exe`/`yt-dlp.exe` puestos junto al exe empaquetado,
`find_ffmpeg()`/`find_ytdlp()` los detectan sin PATH del sistema.

**B2. Adaptar `_add_cuda_dll_dirs` para modo congelado**
En `src/tae/core/transcribe.py:21-46`: si `getattr(sys, "frozen", False)` es
`True`, buscar los DLL de cublas/cudnn en una carpeta bundleada (ej.
`<carpeta del exe>/cuda_dlls`) en vez de `site.getsitepackages()`. En modo
dev (`uv run`) el comportamiento actual no cambia.
Criterio: en el build empaquetado, `os.add_dll_directory` apunta a una ruta
que existe y contiene los `.dll`; transcripción GPU real funciona desde el
`.exe`.

**B3. Adaptar `diarize_wsl.py` para localizar el worker script en modo congelado**
En `src/tae/core/diarize_wsl.py:55-56`: si `sys.frozen`, resolver
`_WORKER_SCRIPT` relativo a la carpeta del ejecutable (donde el script de
build habrá copiado `scripts/wsl_diarize_worker.py`) en vez de
`Path(__file__).resolve().parents[3]`. En modo dev no cambia.
Criterio: con WSL2 configurado, `tae-gui.exe` con `--diarize` corre la
diarización GPU vía WSL2 igual que en `uv run`.

**B4. Crear el script de entrada para PyInstaller**
Nuevo `packaging/entrypoint_gui.py`, thin wrapper:
```python
from tae.gui.app import main

if __name__ == "__main__":
    main()
```
(no duplica `freeze_support()`, ya está dentro de `main()`). PyInstaller
apunta a este archivo en vez de al paquete `tae.gui.app` directamente, para
tener un módulo `__main__` real con el guard estándar.
Criterio: `python packaging/entrypoint_gui.py` arranca la GUI igual que
`uv run tae-gui` en modo no congelado (paridad antes de empaquetar).

### Bloque C — Configuración de PyInstaller

**C1. Escribir `packaging/tae-gui.spec`**
`--onedir`, `--windowed` (sin consola), nombre `tae-gui`, entry point
`packaging/entrypoint_gui.py`. `datas` explícitos para
`src/tae/gui/assets/` y `src/tae/gui/fonts/` (mismo layout relativo que hoy,
para que `Path(__file__).parent / "assets"` siga resolviendo). `datas`
explícito para `scripts/wsl_diarize_worker.py` (copiado a la raíz de la
carpeta de salida, para que B3 lo encuentre).
Criterio: `pyinstaller packaging/tae-gui.spec` corre sin errores y genera
`dist/tae-gui/`.

**C2. Resolver hidden imports / collect-data de dependencias nativas**
Iterar sobre los errores de import faltante al arrancar el `.exe` generado
(`ctranslate2`, `faster-whisper`, `torch`, `whisperx`, `pyannote-audio` y su
árbol — ver versiones en el reporte de exploración) usando
`collect_all`/`hiddenimports` en el `.spec`, hasta que la GUI arranque y una
transcripción + diarización CPU cortas corran sin `ModuleNotFoundError` ni
DLL faltante.
Criterio: `tae-gui.exe` arranca, transcribe un audio corto en GPU, y diariza
en CPU sin errores de import/carga.

### Bloque D — Binarios externos bundleados

**D1. Obtener y ubicar `ffmpeg.exe`/`ffprobe.exe`**
Descargar un build oficial de ffmpeg para Windows (ej. gyan.dev, build
"essentials"), extraer `ffmpeg.exe` y `ffprobe.exe` a la carpeta de salida
del paquete (mismo nivel que `tae-gui.exe`). Documentar la fuente y versión
exacta en `packaging/README.md` (para poder repetir la descarga al
actualizar).
Criterio: los dos binarios están en `dist/tae-gui/` y `ffmpeg -version`
corre desde ahí.

**D2. Obtener y ubicar `yt-dlp.exe`**
Descargar el binario standalone oficial de la release de yt-dlp en GitHub,
ubicarlo junto a `tae-gui.exe`. Documentar en `packaging/README.md` que esto
hay que repetirlo seguido (yt-dlp cambia con frecuencia por el anti-bot de
YouTube — ver P5/P8 en `docs/pendientes.md`).
Criterio: `yt-dlp.exe` está en `dist/tae-gui/` y `yt-dlp --version` corre
desde ahí.

**D3. Copiar los DLL de CUDA (cublas/cudnn) a la carpeta bundleada**
Desde el venv de build, copiar los `.dll` de
`site-packages/nvidia/cublas/bin` y `site-packages/nvidia/cudnn/bin` a
`dist/tae-gui/cuda_dlls/` (la ruta que B2 espera).
Criterio: la carpeta `cuda_dlls` existe con los `.dll` esperados; la
transcripción GPU real usa CUDA (no cae silenciosamente a CPU).

### Bloque E — Script de build reproducible

**E1. Escribir `packaging/build_windows.ps1`**
Un solo comando que: limpia `build/`/`dist/` previos, corre
`uv run --extra diarize pyinstaller packaging/tae-gui.spec`, copia
`ffmpeg.exe`/`ffprobe.exe`/`yt-dlp.exe` (D1/D2) y los DLL de CUDA (D3) al
`dist/tae-gui/` resultante, y al final corre el smoke test (E2).
Criterio: correr `./packaging/build_windows.ps1` desde cero produce
`dist/tae-gui/` completo y funcional sin pasos manuales adicionales.

**E2. Smoke test automatizado post-build**
Script/checklist (puede ser parte del mismo `.ps1` o un script Python
separado) que, sobre el `dist/tae-gui/` recién armado: arranca `tae-gui.exe`
y confirma que el proceso sigue vivo pasados unos segundos (no crashea al
abrir), y opcionalmente corre una transcripción corta de un video de prueba
para confirmar que el subproceso del motor (P12) funciona empaquetado.
Criterio: el build falla visiblemente si el smoke test no pasa, en vez de
darse por bueno solo porque PyInstaller no reportó errores.

### Bloque F — Verificación manual real (Kike)

**F1. Validación manual end-to-end**
Kike copia `dist/tae-gui/` a otra ruta de su máquina, hace doble clic en
`tae-gui.exe`, y corre: (a) transcripción GPU de un video real sin subs,
(b) diarización CPU (`--diarize` sin WSL2 disponible momentáneamente, para
forzar el fallback), (c) diarización GPU vía WSL2 (con el venv Ubuntu ya
configurado, P11), (d) un caso `tae url` con YouTube real. Cancelar a mitad
en al menos un caso (P12).
Criterio: los 4 casos producen las mismas salidas (`.txt`/`.srt`/`.mp3`) y
comportamiento que hoy con `uv run`, sin ventana de terminal visible.

## Nota sobre riesgo técnico

Los ítems más inciertos del plan son **C2** (hidden imports de
torch/whisperx/pyannote — históricamente el punto más frágil de empaquetar
stacks de ML con PyInstaller) y **B2/D3** (DLLs de CUDA). Si alguno resulta
mucho más costoso de lo esperado, vale la pena pausar y avisar antes de
seguir iterando a ciegas.
