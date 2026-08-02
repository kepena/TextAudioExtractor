# Roadmap — TextAudioExtractor

Creado: 2026-07-26
Actualizado: 2026-08-01 (empaquetado en carpeta portable de Windows, build verificado)

## Visión

App de Windows para extraer texto (subtítulos incrustados o transcripción local
con Whisper/GPU) y audio de un video. Motor headless reutilizable + GUI delgada.
Interno ahora, con arquitectura pensada para escalar a producto/servicio.

## Fases

- **Fase 0 — Andamiaje** ✅ CLAUDE.md + docs/ + git local.
- **Fase 1 — Spec** ✅ Spec formal del motor + GUI aprobado (P1). Decidido:
  faster-whisper + PySide6.
- **Fase 2 — Motor (core)** ✅ Detección de subtítulos, extracción de audio,
  transcripción local, salidas (texto plano, `.srt`, audio). Probado como CLI y
  por tests (P3).
- **Fase 3 — GUI delgada** ✅ Arrastrar video (drag-and-drop verificado) → elegir
  salidas → progreso. Verificada end-to-end con voz real en GPU (P4).
- **Fase 4 — Módulo online** ✅ YouTube/plataformas vía `yt-dlp`. Paquete aislado
  `src/tae/online/`, subcomandos `tae local`/`tae url`, playlists en lote, GUI con
  campo URL. Verificado end-to-end en la GUI, incl. cookies y caso de fallo de
  lote. Ver P5 en `docs/pendientes.md`.
- **Fase 5 — Diarización de hablantes** ✅ Camino C (whisperX), opt-in `--diarize`
  / `--speakers` y checkbox en la GUI. Etiquetas `SPEAKER_00:` en `.srt`/`.txt`,
  whisperx como extra opcional + token HF de setup. Implementada por bloques A→F
  (`docs/plans/2026-07-28-diarizacion-progreso.md`) y verificada end-to-end el
  2026-07-29 (audio de 2 voces → 2 hablantes coherentes). Ver P10.
  - **GPU vía WSL2** ✅ (P11, 2026-07-31): `core/diarize_wsl.py` detecta si WSL2 +
    venv de diarización + GPU están listos y, si sí, cruza a un subproceso
    `wsl.exe` (Ubuntu, whisperX 3.8 + torch cu128 — ahí `k2` sí tiene ruedas, a
    diferencia de Windows) en vez de diarizar en CPU. Si algo falta, degrada solo
    a CPU sin bloquear. Verificado con video real de 7 hablantes: coherente,
    ~8 min primera corrida (con descarga de pesos); cancelar corta en ~6.5s sin
    procesos huérfanos en WSL2. Setup: `scripts/wsl_diarize_setup.sh`. Spec/plan:
    `docs/specs/2026-07-30-diarizacion-gpu-wsl2.md`,
    `docs/plans/2026-07-30-diarizacion-gpu-wsl2.md`.
  - **CPU sigue como fallback automático** cuando WSL2/GPU no están disponibles
    (la transcripción sigue en GPU aparte). Detalle completo, bugs reales
    encontrados (wsl.exe, pip, bash) y opciones descartadas en **P11**.
- **Fase 6 — Cancelar inmediato** ✅ La GUI corre el motor en un subproceso que mata
  al cancelar. Implementada y verificada (P12, 2026-07-30): diarización cancelada a
  mitad → corte en 0.11 s, sin salidas a medias; corrida normal intacta; `spawn` no
  relanza la GUI. `pytest` 101/101. Spec/plan:
  `docs/specs/2026-07-30-cancelar-inmediato.md`,
  `docs/plans/2026-07-30-cancelar-inmediato.md`.
- **Fase 7 — Empaquetado en carpeta portable de Windows** ✅ código y build
  verificados (2026-08-01); falta solo la validación manual real de Kike
  (transcripción/diarización/YouTube/cancelar desde el `.exe`). PyInstaller
  `--onedir` (`packaging/tae-gui.spec`), `ffmpeg`/`ffprobe`/`yt-dlp` y whisperx
  (diarización CPU fallback) bundleados, script de build reproducible
  (`packaging/build_windows.ps1`) con smoke test automático. En el camino se
  encontró y corrigió que el venv de este repo no puede vivir en `G:` (unidad de
  red) — ver P13. `pytest` 115/115, `ruff` limpio. Spec/plan:
  `docs/specs/2026-08-01-empaquetado-windows-portable.md`,
  `docs/plans/2026-08-01-empaquetado-windows-portable.md`.

## Decisiones tomadas (brainstorm 2026-07-26)

- Camino 3: motor headless + GUI delgada.
- Transcripción **local** con Whisper, GPU NVIDIA disponible.
- "Ambas": extraer subtítulos si el video los trae; si no, transcribir.
- No reutilizar la app de descargas previa.
- Fuera de alcance: edición de video y transcripción en la nube.
