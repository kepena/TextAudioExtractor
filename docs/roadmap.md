# Roadmap — TextAudioExtractor

Creado: 2026-07-26
Actualizado: 2026-07-26

## Visión

App de Windows para extraer texto (subtítulos incrustados o transcripción local
con Whisper/GPU) y audio de un video. Motor headless reutilizable + GUI delgada.
Interno ahora, con arquitectura pensada para escalar a producto/servicio.

## Fases

- **Fase 0 — Andamiaje** ✅ CLAUDE.md + docs/ + git local.
- **Fase 1 — Spec** ⏳ Spec formal del motor + GUI con `k-design-specs`. Approval
  gate: no se implementa hasta que Kike apruebe.
- **Fase 2 — Motor (core)** Detección de subtítulos, extracción de audio,
  transcripción local, salidas (texto plano, `.srt`, audio). Probado como CLI.
- **Fase 3 — GUI delgada** Arrastrar video → elegir salidas → progreso.
- **Fase 4 — Módulo online (opcional)** YouTube/plataformas vía `yt-dlp`.

## Decisiones tomadas (brainstorm 2026-07-26)

- Camino 3: motor headless + GUI delgada.
- Transcripción **local** con Whisper, GPU NVIDIA disponible.
- "Ambas": extraer subtítulos si el video los trae; si no, transcribir.
- No reutilizar la app de descargas previa.
- Fuera de alcance: edición de video y transcripción en la nube.
