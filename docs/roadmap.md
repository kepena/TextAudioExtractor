# Roadmap — TextAudioExtractor

Creado: 2026-07-26
Actualizado: 2026-07-27 (MVP + módulo online verificados end-to-end en la GUI)

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
- **Fase 5 — Diarización de hablantes** 🔨 Camino C (whisperX), opt-in `--diarize`.
  Spec + plan aprobados (P10). Ejecución por bloques A→F en
  `docs/plans/2026-07-28-diarizacion-progreso.md`.

## Decisiones tomadas (brainstorm 2026-07-26)

- Camino 3: motor headless + GUI delgada.
- Transcripción **local** con Whisper, GPU NVIDIA disponible.
- "Ambas": extraer subtítulos si el video los trae; si no, transcribir.
- No reutilizar la app de descargas previa.
- Fuera de alcance: edición de video y transcripción en la nube.
