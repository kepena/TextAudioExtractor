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
- **P4** ✅ GUI verificada end-to-end con voz real (2026-07-27, `Esfuerzo.mp4`,
  1:13, sin subs → Whisper GPU). Validado por control de escritorio: carga por
  diálogo, probe correcto (duración/subs/audio), carpeta de salida auto, las 3
  salidas generadas en disco (.txt/.srt/.mp3, transcripción ES precisa), barra
  0→100%, etiquetas de etapa ("Transcribiendo…", "Listo: … idioma es"), bloqueo
  de inputs en running, **Abrir carpeta** OK, **Cancelar** a mitad limpio (mensaje
  "Cancelado. No se generaron archivos válidos." + reset a 0%, sin corromper la
  corrida previa), render de marca impecable. No probado: *drag-drop* (se usó el
  diálogo "Elegir archivo" por fiabilidad de la automatización).
- **P5** ✅ Módulo YouTube/online con `yt-dlp` implementado (2026-07-26). Paquete
  aislado `src/tae/online/` (verificación de yt-dlp, errores tipados con causa,
  descarga audio+subs, `parse_vtt` en el core, runners video/playlist, naming),
  subcomandos `tae local` / `tae url`, y cableado en la GUI (campo URL + opciones).
  `pytest` 55/55, `ruff` limpio. Red real verificada: caso 1 (subs del creador →
  sin Whisper) y caso 2/3 (`--force-transcribe` → Whisper GPU) con "Me at the zoo".
  Falta prueba de red de una playlist real con fallo (caso 4): la lógica está en
  unit test y la clasificación de fallo real quedó probada; queda correr una
  playlist end-to-end cuando haya una URL. Ver `docs/plans/2026-07-27-modulo-online-youtube.md`.
  **Actualización 2026-07-27:** ambos caminos online verificados end-to-end **en la
  GUI**: (b) sin subs → Whisper (video local servido por HTTP en localhost, para
  evitar el bloqueo de YouTube) y (a) subs del creador → sin Whisper (TED talk,
  .srt/.txt derivados de la pista de subs, sin transcribir). También verificada la
  ruta de error de la GUI: diálogo claro y clasificado, sin crash. Sigue pendiente
  el **caso 4 (playlist real)**: hoy YouTube bloquea esta máquina (ver P8).
- **P6** ⏳ Kike debe colocar el logo real en
  `src/tae/gui/assets/kaiketek-logo.png` (PNG con transparencia). El código ya lo
  detecta solo; mientras tanto usa `tree.svg` de respaldo.
- **P7** ✅ Bug de parseo VTT encontrado y corregido (2026-07-27) durante la
  verificación online con un TED talk. `parse_vtt`/`parse_srt` asumían **un solo
  timestamp por bloque**; los VTT de TED (y otros "rolling captions") pegan varios
  cues sin línea en blanco, así que el segundo `-->` se colaba como texto y se
  duplicaban líneas. Fix en `src/tae/core/subtitles.py`: motor común `_parse_cues`
  que recorre todos los timestamps del bloque, descarta cues degenerados (texto
  vacío) y duplicados idénticos consecutivos. Verificado contra el VTT real de TED
  (427 segmentos, 0 timestamps colados). `pytest` 57/57 (+2 tests de regresión),
  `ruff` limpio.
- **P8** ⏳ Limitación del módulo online: **no pasa cookies a `yt-dlp`**. YouTube
  hoy exige login/verificación anti-bot para esta máquina (`HTTP 429` +
  "Sign in to confirm you're not a bot" + aviso de que falta un runtime JS/deno),
  así que los videos de YouTube quedan inaccesibles desde la app aunque la ruta de
  error avise correctamente. Decidir si se agrega soporte `--cookies-from-browser`
  (y/o instalar `deno`) para el módulo online. Es bloqueo externo + brecha de
  robustez, no un bug del código.
