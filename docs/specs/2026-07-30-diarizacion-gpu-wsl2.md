# Spec — Diarización de hablantes en GPU vía WSL2

Fecha: 2026-07-30
Origen: brainstorm de la misma sesión, P11 en `docs/pendientes.md`.

## 1. Overview

Hoy la diarización de hablantes (P10, whisperX) corre en CPU porque el extra
`torch` que instala Windows es CPU-only: `torchaudio+cu128` en Windows enruta por
`k2`, que no tiene ruedas para esa plataforma. En Linux sí hay ruedas de `k2`, así
que esta feature mueve **solo la diarización** a un subproceso que corre dentro de
WSL2 (Ubuntu), donde el mismo stack (whisperX 3.8 + torch cu128) sí usa la GPU. La
GUI, la transcripción, la extracción de subtítulos/audio y el resto del motor
siguen igual, en Windows. El disparador es que la diarización en CPU es "no
tolerable" para el uso real: un video de 1-2 horas tarda hasta 8 horas en CPU.

## 2. Usuarios Específicos

- Kike, en su propia máquina Windows con WSL2 (Ubuntu) ya instalado y la RTX 4050
  ya visible dentro de esa distro (`nvidia-smi` confirmado). Único usuario de esta
  v1 — la app sigue de uso interno de Kaiketek, no hay distribución a otras
  máquinas todavía.

## 3. Contexto del Problema

- P10 dejó la diarización funcional pero en CPU (~130 s para 28 s de audio). Para
  los videos reales que usa Kike (1-2 horas), eso escala a horas de espera —
  inviable para uso regular.
- P11 investigó subir la diarización a GPU sin salir de Windows y encontró un
  callejón sin salida: `k2` (dependencia de `torchaudio` cuando detecta CUDA) no
  tiene ruedas para Windows, y el único combo de versiones viejas que sí evitaba
  `k2` (whisperX 3.1.1) está retirado (yanked) del índice de paquetes y arrastra un
  ecosistema de dependencias obsoleto que no arranca.
- WSL2 destraba esto porque ahí `k2` sí tiene ruedas — el mismo stack moderno que
  ya se usa en Windows para transcripción (torch cu128) funciona para diarización
  sin bajar versiones ni adoptar paquetes retirados.

## 4. Alcance Versión 1

**Sí incluye:**

- Un nuevo camino de ejecución para la diarización: en vez de correr
  `core/diarize.py` dentro del subproceso Windows actual (P12), la GUI invoca
  `wsl.exe -d Ubuntu -- python ...` para correr la diarización dentro de esa
  distro, cuando el usuario pidió diarización (`--diarize` / checkbox ya existente
  de P10).
- Traspaso de entrada/salida por archivos en una carpeta compartida (no hay
  streaming de datos por stdin/stdout ni servicio de red): el audio a diarizar se
  deja en una ruta visible desde ambos lados (Windows vía `\\wsl$\<distro>\...` o
  WSL2 vía `/mnt/c/...`), y el resultado (segmentos con hablante asignado) vuelve
  por el mismo mecanismo.
- Reporte de progreso/etapas equivalente al que ya existe hoy para diarización en
  CPU (transcribir/alinear/diarizar), traducido a las mismas señales Qt que usa
  `_EngineBridge` (`stage`, `info`, `progress`).
- Cancelar (P12): matar el proceso `wsl.exe` desde Windows corta la diarización de
  inmediato, igual que hoy mata el subproceso Windows.
- Detección de si WSL2 + la distro + GPU están realmente disponibles, con
  degradación explícita: si no lo están, la diarización sigue corriendo en CPU
  dentro de Windows como hoy (invariante 3: GPU es supuesto de rendimiento, no
  requisito de arranque), avisando al usuario que va a ser lenta.
- Instrucciones o script de setup del lado Ubuntu (venv, whisperX 3.8 + torch
  cu128, token de HuggingFace) — equivalente al setup que ya existe para el extra
  `diarize` en Windows, pero para la distro.

**No incluye (fuera de alcance v1):**

- Mover la transcripción, extracción de subtítulos/audio, o cualquier otra parte
  del motor a WSL2. Solo la diarización cruza la frontera.
- Mover la GUI a WSL2/Linux (nada de WSLg, X server, etc.).
- Instalar o configurar WSL2 desde cero: ya está instalado y con GPU visible en
  esta máquina; el trabajo asume ese punto de partida.
- Un servicio persistente en WSL2 con el modelo ya cargado en memoria (se evaluó
  en el brainstorm y se descartó para v1 por la complejidad de ciclo de vida/IPC
  que suma frente al subproceso simple).
- Empaquetar o distribuir esto para que corra en la máquina de otro usuario
  (futuro SaaS): se resuelve más adelante, no condiciona esta v1.
- Cambios al formato de salida (`.srt`/`.txt` con `SPEAKER_00:`, etc.): la v1 solo
  cambia *dónde* corre el cómputo, no el resultado ni su formato.

## 5. Comportamiento Esperado

- El usuario marca diarización (checkbox/flag) exactamente como hoy — no hay UI
  nueva para "elegir GPU vs CPU" ni para configurar WSL2 a mano.
- Al arrancar un job con diarización, la app detecta automáticamente si el camino
  GPU-por-WSL2 está disponible (WSL2 presente, distro configurada instalada y con
  el entorno de diarización listo, GPU visible desde ahí). Si sí:
  - La GUI muestra etapas equivalentes a las actuales ("Transcribiendo e
    identificando hablantes...", con el mismo aviso de "Diarizando en GPU" que hoy
    usa `on_info` en `diarize.py`, ahora reportado desde WSL2 pero mostrado igual
    en la interfaz de Windows).
  - El tiempo de proceso baja de horas a un rango comparable al de la transcripción
    en GPU (mismo orden de magnitud que hoy tarda transcribir, no minutos extra por
    hablante).
- Si el camino GPU-por-WSL2 **no** está disponible (WSL2 no instalado, distro
  faltante, entorno de diarización no configurado en Ubuntu, o GPU no visible
  desde ahí), la app degrada automáticamente al camino CPU actual (dentro del
  subproceso Windows de P12), con el mismo aviso ya existente de "no se detectó
  GPU, la diarización correrá en CPU y será notablemente lenta". El usuario nunca
  ve un error duro por esto — como mucho, ve que fue lento.
- Cancelar durante una diarización en WSL2 se comporta igual que hoy: corte
  inmediato, sin salidas a medias, sin dejar procesos huérfanos corriendo dentro de
  WSL2 (el proceso `wsl.exe` y lo que lanzó adentro deben morir con él).
- Al terminar (éxito o cancelación), no quedan archivos temporales en la carpeta
  compartida entre Windows y WSL2 — se limpian igual que hoy se limpia `job_tmp`.

## 6. Posibles Errores y Mitigaciones

- **WSL2 no instalado o distro no encontrada:** la app no falla ni bloquea el
  arranque; degrada a diarización en CPU con el aviso ya existente. No se intenta
  instalar WSL2 automáticamente.
- **Entorno de diarización no configurado dentro de Ubuntu** (venv faltante,
  whisperX no instalado, token de HuggingFace no configurado ahí): mismo criterio
  — degrada a CPU con aviso, en vez de un traceback. El mensaje debe distinguir
  este caso ("GPU vía WSL2 no disponible: falta configurar el entorno") del caso
  genérico de "no hay GPU" para que quede claro qué hay que arreglar si se quiere
  GPU.
- **`wsl.exe` no responde o cuelga al arrancar** (ej. WSL2 en mal estado): se trata
  como fallo de ese camino con timeout razonable, y cae a CPU con aviso — no deja
  la app colgada esperando indefinidamente.
- **Cancelar a mitad de una diarización en WSL2:** debe matar tanto el proceso
  `wsl.exe` en Windows como el proceso Python que quedó corriendo dentro de la
  distro, para no dejar cómputo huérfano consumiendo GPU/CPU en Ubuntu.
- **Carpeta compartida no accesible desde un lado** (permisos, ruta `\\wsl$` no
  resuelve, etc.): error claro y legible en la GUI, sin traceback crudo; se trata
  como fallo de configuración del camino GPU, con la misma degradación a CPU si es
  posible, o un mensaje claro si ni CPU puede completar el traspaso de archivos
  (caso extremo, poco probable ya que CPU corre dentro del mismo Windows).
- **Resultado corrupto o parcial desde WSL2** (proceso murió a mitad sin avisar):
  se detecta como fallo (no se asume éxito por la sola presencia de un archivo de
  salida) y se reporta como error del job, igual que hoy un crash del subproceso
  Windows se reporta como "El proceso del motor terminó inesperadamente."

---

**¿Este spec queda aprobado tal cual, o hay algo que ajustar antes de pasar al
plan?**
