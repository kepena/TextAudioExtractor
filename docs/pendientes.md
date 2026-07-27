# Pendientes — TextAudioExtractor

Lista **numerada y estable**: los números **no se reciclan**. Un pendiente
cerrado se marca ✅ y se resume, pero conserva su número para siempre — así
"vamos con el P3" significa lo mismo en cualquier sesión. **Es la lista viva:
léela primero.**

---

- **P1** ✅ Spec del motor + GUI aprobado (2026-07-26). Decidido: faster-whisper +
  PySide6. Ver `docs/specs/2026-07-26-extractor-texto-audio-mvp.md`.
- **P2** ✅ Plan de implementación generado y confirmado (2026-07-26). Ver
  `docs/plans/2026-07-26-extractor-texto-audio-mvp.md`.
- **P3** ✅ MVP implementado (2026-07-26): motor `core` + CLI + GUI PySide6 + tests.
  Verificado: `pytest` 17/17, `ruff` limpio, transcripción end-to-end en GPU
  (RTX 4050, CUDA/float16). Ver `docs/plans/2026-07-26-extractor-texto-audio-mvp.md`.
- **P4** ⏳ Probar la GUI (`uv run tae-gui`) con un video real de voz y validar el
  flujo visual completo (arrastrar → salidas → carpeta → progreso → abrir carpeta).
- **P5** ⏳ (Fase posterior) Módulo YouTube/online con `yt-dlp`.
