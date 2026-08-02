# Spec — Empaquetado de TextAudioExtractor como carpeta portable de Windows

## Overview

TextAudioExtractor hoy solo corre vía `uv run` desde terminal, lo que exige
tener Python, `uv` y el venv del proyecto configurados. Este spec cubre
empaquetar la GUI como una **carpeta portable de Windows** (PyInstaller
`--onedir`) con un `tae-gui.exe` que arranca con doble clic, sin terminal ni
Python instalado aparte. Incluye `ffmpeg`/`yt-dlp` bundleados, la diarización
CPU (whisperx, P10) como fallback dentro del paquete, y un script de build que
reconstruye la carpeta final con un solo comando.

## Usuarios Específicos

Kike, en su propia máquina Windows (RTX 4050 NVIDIA, con el venv Ubuntu de
diarización GPU vía WSL2 ya configurado — P11). Es el único usuario
contemplado en esta v1; no está pensado para distribuir a otras personas de
Kaiketek ni a clientes.

## Contexto del Problema

Usar la app hoy requiere abrir una terminal y correr `uv run tae-gui` (o el
CLI). Es fricción para el uso interno cotidiano de Kike — quiere un
ejecutable que arranque como cualquier programa normal de Windows.

## Alcance Versión 1

**Sí incluye:**

- Carpeta portable generada con PyInstaller `--onedir`, con `tae-gui.exe`
  (GUI) como punto de entrada.
- `ffmpeg.exe` y `yt-dlp.exe` bundleados dentro de la misma carpeta (no
  dependen del PATH del sistema).
- El extra de diarización CPU (`whisperx` + dependencias, P10) incluido en el
  bundle, para que el fallback sin WSL2 siga funcionando igual que hoy.
- Descarga de pesos de modelo (Whisper, pyannote) en el primer uso — mismo
  comportamiento que hoy, requiere internet la primera vez que se transcribe
  o diariza.
- Script de build (ubicación y nombre exacto a definir en el plan) que en un
  solo comando: limpia el build anterior, corre PyInstaller, copia
  `ffmpeg.exe`/`yt-dlp.exe` a la carpeta de salida, y deja el paquete final
  listo para moverse a otra ruta.
- La detección de GPU/CUDA (invariante 3) y de WSL2/venv de diarización (P11)
  siguen funcionando igual que en código fuente: sin GPU → CPU para
  transcripción; sin WSL2 configurado → diarización cae a CPU (whisperx
  bundleado) en vez de fallar duro.

**No incluye (fuera de alcance v1):**

- Instalador con asistente (Inno Setup), accesos directos de menú inicio,
  desinstalador. Se decidió carpeta portable, no instalador de verdad.
- Automatizar el setup de WSL2/GPU para diarización. Sigue siendo el proceso
  manual existente (`scripts/wsl_diarize_setup.sh`).
- Bundlear los pesos de modelos Whisper/pyannote dentro del paquete. Se
  descargan en el primer uso, como hoy.
- Empaquetar el CLI (`tae.exe`). El CLI ya corre por terminal; no aplica el
  objetivo "sin terminal" de este spec.
- Firma de código o mitigar advertencias de SmartScreen/antivirus.
- Soporte para máquinas sin GPU NVIDIA distintas a la de Kike, o para otros
  usuarios de Kaiketek. Queda para una v2 si algún día se decide distribuir.
- Auto-actualización del paquete o del `yt-dlp` bundleado. Actualizar es un
  rebuild manual.

## Comportamiento Esperado

- Kike copia/mueve la carpeta del paquete a donde quiera en su máquina y hace
  doble clic en `tae-gui.exe`. La GUI arranca igual que hoy vía
  `uv run tae-gui`, sin ventana de terminal visible y sin Python instalado
  aparte.
- Todo el flujo de la GUI (carga por diálogo o drag&drop, detección de subs,
  transcripción GPU, diarización, exportar `.txt`/`.srt`/`.mp3`, cancelar)
  se comporta exactamente igual que en la versión `uv run` — el empaquetado
  cambia solo el arranque, no el comportamiento.
- Si Kike marca "diarizar" y WSL2/el venv de diarización GPU no está
  disponible, la app degrada a diarización CPU con el whisperx bundleado,
  con el mismo comportamiento y mensajes que hoy en el venv de desarrollo.
- Si faltan los pesos del modelo (primera vez), la app los descarga como hoy;
  necesita internet en ese momento.
- Cuando Kike necesite reconstruir el paquete (tras actualizar `yt-dlp` o el
  código de la app), corre el script de build con un solo comando y obtiene
  la carpeta final lista, sin pasos manuales de copiar binarios.

## Posibles Errores y Mitigaciones

- **SmartScreen/antivirus marca el `.exe` como desconocido** (típico de
  binarios PyInstaller sin firmar): Kike permite la ejecución manualmente la
  primera vez. Se documenta como nota conocida, no como bug a resolver en v1.
- **Falta `ffmpeg.exe` o `yt-dlp.exe`** en la carpeta (se movió/borró algo):
  la app debe seguir mostrando el mismo error claro de "binario no
  encontrado" que hoy (invariante 5), no un traceback crudo.
- **El build de PyInstaller no empaqueta bien algún hook nativo**
  (`ctranslate2`, `torch`, `pyannote`) y el `.exe` falla al arrancar o al
  transcribir aunque en `uv run` funcione: el script de build corre un smoke
  test básico (arrancar la GUI y/o una transcripción corta) antes de darse
  por bueno, para no descubrir el problema recién en uso real.
- **Rutas con espacios/caracteres especiales**: el repo vive en
  `G:\Unidades compartidas\...` (con espacios). Verificar que PyInstaller y
  el script de build no rompan por eso.
- **`yt-dlp` bundleado queda desactualizado** y YouTube empieza a bloquear
  descargas: mismo comportamiento de error clasificado que existe hoy
  (P5/P8), más la nota operativa de que toca reconstruir el paquete con
  `yt-dlp` actualizado.
- **El paquete final resulta pesado** (varios GB por CUDA + whisperx CPU +
  torch): no es un error funcional, se documenta como expectativa — no es un
  `.exe` liviano.
