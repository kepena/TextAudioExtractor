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
  ruta de error de la GUI: diálogo claro y clasificado, sin crash.
  **Caso 4 cerrado (2026-07-27):** corrida real de `run_playlist` sobre una
  playlist de YouTube (acotada a 3 ítems: 2 válidos + 1 `[Deleted video]`). El
  `BatchReport` dio 2 éxitos (con nombres `NN_`) + 1 fallo clasificado como
  `unavailable`, sin abortar el lote. Esa corrida destapó el bug del `live_chat`
  (ver P9). Nota: el "bloqueo de YouTube" resultó **intermitente** (anti-bot), no
  duro; con reintento funciona.
- **P6** ✅ Logo real colocado (2026-07-27) en `src/tae/gui/assets/kaiketek-logo.png`
  (256×256, fondo transparente, 43 KB). Origen: `LogoKaiketekTransparente.png` del
  repositorio de Marca (el árbol solo, sin wordmark), auto-recortado al contenido
  para que llene el ícono. Ahora se usa en el footer ("Powered by · árbol · KAIKETEK")
  y como ícono de ventana/taskbar. `_find_logo()` lo detecta primero; `tree.svg`
  queda como respaldo. El ícono grande del header sigue con `appicon.svg` (no se
  pidió cambiarlo).
- **P7** ✅ Bug de parseo VTT encontrado y corregido (2026-07-27) durante la
  verificación online con un TED talk. `parse_vtt`/`parse_srt` asumían **un solo
  timestamp por bloque**; los VTT de TED (y otros "rolling captions") pegan varios
  cues sin línea en blanco, así que el segundo `-->` se colaba como texto y se
  duplicaban líneas. Fix en `src/tae/core/subtitles.py`: motor común `_parse_cues`
  que recorre todos los timestamps del bloque, descarta cues degenerados (texto
  vacío) y duplicados idénticos consecutivos. Verificado contra el VTT real de TED
  (427 segmentos, 0 timestamps colados). `pytest` 57/57 (+2 tests de regresión),
  `ruff` limpio.
- **P8** ✅ Soporte de cookies + detección de runtime JS (2026-07-27). Decidido con
  Kike: (a) **un solo campo `cookies` configurable** que acepta nombre de navegador
  (`firefox`/`chrome`/`edge`, con spec `browser[:profile]`) → `--cookies-from-browser`,
  o cualquier otra cosa (ruta a `cookies.txt`) → `--cookies FILE`; helper
  `cookie_args()` en `ytdlp_utils`, cableado a las 3 invocaciones de yt-dlp
  (`probe_url`, `_fetch_metadata`, `download`) y propagado por el runner (incluida la
  reconstrucción por-entrada del lote). (b) **Runtime JS: detectar y avisar** (estilo
  invariante 5, sin bundlear): `find_js_runtime()` busca deno/node/bun; si falta,
  CLI y GUI emiten `JS_RUNTIME_HINT` una vez por corrida (no revienta). Flag CLI
  `tae url --cookies`, campo en la GUI (con tooltip: en Windows Firefox es el más
  fiable, Chrome/Edge cifran cookies). Mensajes `NEEDS_LOGIN`/`EXTRACTOR_ERROR`
  actualizados para apuntar al campo de cookies y a deno. `pytest` 76/76 (+16),
  `ruff` limpio. Nota: esta máquina ya tiene Node en el PATH, así que el requisito
  de runtime JS de YouTube está cubierto. Falta una prueba de red real con un video
  de YouTube usando cookies del navegador (queda para cuando Kike la quiera correr).
- **P9** ✅ Bug del `live_chat.json` encontrado y corregido (2026-07-27) durante el
  caso 4. En videos que fueron premiere/directo, yt-dlp deja un `id.live_chat.json`
  (chat en vivo) como sidecar: (1) `_choose_subtitle` lo elegía vía
  `next(iter(manual))` y yt-dlp lo descargaba, y (2) `_locate_audio` solo excluía
  `.vtt/.srt`, así que tomaba el `.live_chat.json` como audio → ffmpeg reventaba
  ("Invalid data found"). Fix en `src/tae/online/download.py`: ignorar el
  pseudo-idioma `live_chat` al elegir subtítulo, y en `_locate_audio` excluir todos
  los sidecars (json/miniaturas/…) y quedarse con el archivo más grande (el medio
  real pesa MB). Verificado en vivo: "Hensonn-Sahara" (que fallaba) ahora genera su
  mp3. `pytest` 60/60 (+3 tests), `ruff` limpio.
