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
  UI ya rebrandeada a Kaiketek (tema claro, colores, Montserrat/Poppins empaquetadas,
  ícono de app, footer "Powered by"); falta la corrida real con voz.
- **P5** ✅ Módulo YouTube/online con `yt-dlp` implementado (2026-07-26). Paquete
  aislado `src/tae/online/` (verificación de yt-dlp, errores tipados con causa,
  descarga audio+subs, `parse_vtt` en el core, runners video/playlist, naming),
  subcomandos `tae local` / `tae url`, y cableado en la GUI (campo URL + opciones).
  `pytest` 55/55, `ruff` limpio. Red real verificada: caso 1 (subs del creador →
  sin Whisper) y caso 2/3 (`--force-transcribe` → Whisper GPU) con "Me at the zoo".
  Falta prueba de red de una playlist real con fallo (caso 4): la lógica está en
  unit test y la clasificación de fallo real quedó probada; queda correr una
  playlist end-to-end cuando haya una URL. Ver `docs/plans/2026-07-27-modulo-online-youtube.md`.
- **P6** ⏳ Kike debe colocar el logo real en
  `src/tae/gui/assets/kaiketek-logo.png` (PNG con transparencia). El código ya lo
  detecta solo; mientras tanto usa `tree.svg` de respaldo.
