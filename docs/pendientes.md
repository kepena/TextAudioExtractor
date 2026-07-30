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
  corrida previa), render de marca impecable.
  **Drag-drop verificado (2026-07-27):** se arrastró un `.mp4` real desde el
  Explorador a la zona de drop (control de escritorio). `DropFrame.dropEvent`
  recibió la URL, filtró por `VIDEO_EXTS` y cargó igual que por diálogo: probe
  correcto (0:06, sin subs, con audio), carpeta de salida auto, y generó el
  audio en disco (`prueba_dragdrop.mp3`, 6.04 s). Sin cambios de código. Nota de
  automatización: conducir un OLE drag cross-proceso con computer-use es frágil
  (la ventana overlay de arrastre de Windows queda en primer plano y bloquea los
  movimientos intermedios); lo que funcionó fue un `left_click_drag` único
  (press→move→release nativo en un solo paso). P4 cerrado por completo.
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
  actualizados para apuntar al campo de cookies y a deno. `pytest` 78/78 (+18),
  `ruff` limpio. Nota: esta máquina ya tiene Node en el PATH, así que el requisito
  de runtime JS de YouTube está cubierto.
  **Verificado en red real (2026-07-27):** "Me at the zoo" descargado end-to-end
  por la app (subs del creador → .txt/.srt/.mp3). Descubierto en la prueba: en esta
  máquina Windows **ningún navegador deja leer cookies directo** (Firefox/Chrome no
  instalados; Edge/Brave cifran la BD → "Could not copy Chrome cookie database").
  Se añadió `FailureCause.COOKIES_ERROR`: antes ese fallo caía en "causa no
  identificada"; ahora la app avisa claro y recomienda exportar un `cookies.txt`.
  **Verificado con cookies reales (2026-07-27):** Kike exportó su `cookies.txt` de
  Brave con la extensión "Get cookies.txt LOCALLY" y la corrida generó .txt/.srt/.mp3
  sin romperse. Hallazgo clave del setup de Kike: el **navegador principal es Brave**,
  y en su Windows `--cookies-from-browser brave` NO sirve (abierto → base bloqueada;
  cerrado → lee cookies pero YouTube devuelve "No video formats found"); en cambio el
  **`cookies.txt` exportado sí funciona**. Recomendación operativa: dejar el campo de
  cookies vacío para videos normales (hoy la máquina no está bloqueada), y usar
  `cookies.txt` (de una cuenta **desechable**, no la principal de Google) solo cuando
  un video exija login/edad o vuelva el anti-bot. Feature cerrado; queda opcional
  probar un video con restricción de edad real. Además: **yt-dlp no es dependencia
  pip** (invariante 5) y un `uv sync` lo borra del venv; reinstalar con
  `uv pip install -U yt-dlp --python "C:/Users/kepen/.venvs/unidadso-ordenes/Scripts/python.exe"`.
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
- **P10** ✅ Diarización de hablantes (Camino C, whisperX). Opt-in `--diarize`/checkbox,
  whisperX solo con el flag, `Segment.speaker`, salidas `SPEAKER_00:`, `--speakers N`,
  whisperx como extra opcional + token HF de setup, degradar sin GPU. Implementado en
  bloques A→F (ver `docs/plans/2026-07-28-diarizacion-progreso.md`) y **verificado
  end-to-end (2026-07-28)**: audio real de 2 voces → 2 `SPEAKER_xx` coherentes,
  `--speakers 2` respetado, formato spec §5. En k-verify se destaparon y arreglaron 3
  bugs de integración con whisperX 3.4 (device desde torch, kwarg `token=` del
  constructor, modelo por defecto `speaker-diarization-community-1`). Nota de setup:
  el `--extra diarize` instala torch **CPU-only**, así que la diarización corre en CPU
  aunque faster-whisper use GPU; para GPU en diarización haría falta el torch CUDA
  (pendiente menor, no bloquea). `pytest` 92/92, `ruff` limpio. Ver P11 para el torch CUDA.
- **P11** ⛔ Torch CUDA para diarización en GPU — **intentado y revertido
  (2026-07-29): bloqueado en Windows por `k2`.** El `--extra diarize` resuelve
  `torch` a la rueda **CPU-only** (`+cpu`), así que whisperX diariza en CPU (lento,
  ~130 s para 28 s de audio) aunque la RTX 4050 la use faster-whisper. Se probó
  fijar torch/torchaudio/torchvision al índice CUDA de PyTorch (`cu128`) vía
  `[tool.uv.sources]` + `[[tool.uv.index]]`. `_torch_device()` pasó a `cuda` y se
  destaparon (y en su momento se arreglaron) dos incompatibilidades de la cadena
  CUDA: (a) `torch.load` con `weights_only=True` por defecto en torch≥2.6 rompe los
  checkpoints de pyannote/VAD → se necesita forzar `weights_only=False`; (b) **la
  rueda `torchaudio 2.8+cu128`, al detectar CUDA, enruta por un decoder que importa
  `k2`**, y `k2` no tiene ruedas para Windows (se compila desde fuente con CUDA,
  inviable en la práctica). La rueda `torchaudio +cpu` no toca `k2`, por eso el
  camino CPU funciona. Como whisperX 3.8 fija `torch~=2.8`, no se puede bajar torch
  sin bajar whisperX. **Estado: revertido al stack CPU commiteado (verificado en
  verde, 2 voces coherentes).**
  - **Opción 1 (combo viejo whisperX 3.1.1 + torch 2.2.2+cu121) — PROBADA en venv
    aislado el 2026-07-29: NO funciona.** torch cu121 instala y CUDA se detecta,
    pero whisperX 3.1.1 está **yanked** (build no oficial de terceros) y exige
    resucitar todo su ecosistema de época (numpy<2, transformers 4.36/4.39,
    pyannote 3.1.1). Con ese set, `transformers` revienta al importar por la
    combinación de deps opcionales de pyannote (scipy/librosa presentes,
    essentia/pretty_midi no) → `ImportError` del dummy de Pop2Piano, reproducible en
    venv limpio con 4.36.2 y 4.39.3. Callejón sin salida; no se adopta un paquete
    yanked con deps obsoletas en el repo.
  - **Opción 2 (WSL2) — camino GPU recomendado si se retoma.** En Linux hay ruedas
    de `k2`, así que el stack **moderno** actual (whisperX 3.8 + torch cu128)
    correría en GPU sin bajar nada ni tocar paquetes yanked.
  - **Opción 3 (CPU) — estado actual.** Diarización en CPU (funciona y verificada);
    la transcripción sigue en GPU. No bloquea P10.
- **P12** 🔨 Cancelar inmediato en la diarización. Hoy `should_cancel` solo se
  consulta **entre etapas**; en la diarización las llamadas de whisperX
  (transcribe/align/diarizar) son nativas y monolíticas, así que sobre un archivo
  largo "Cancelar" queda pendiente hasta que termina la etapa en curso (verificado
  en la prueba de GUI del 2026-07-29 con un video de 84 min). **Decidido con Kike
  (opción A): correr el motor en un subproceso y matarlo al cancelar** — corte
  inmediato y limpio, sin arriesgar el estado de torch/CUDA del proceso GUI
  (opción B, `QThread.terminate()`, descartada por inestable). Las salidas ya van a
  disco; solo hay que pasar progreso/etapas por una cola. Toca `gui/worker.py`
  (y CLI si se quiere el mismo corte).
  **Spec aprobado (2026-07-30):** `docs/specs/2026-07-30-cancelar-inmediato.md`
  (GUI solo, todos los jobs, cerrar ventana cancela). **Plan:**
  `docs/plans/2026-07-30-cancelar-inmediato.md` (módulo `gui/engine_process.py` +
  puente `_EngineBridge` en `worker.py` + `freeze_support`/`closeEvent`). Falta
  implementar y verificar.
