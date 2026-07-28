# Progreso — Diarización de hablantes (ejecución por sesiones)

Archivo de handoff para implementar la diarización **en sesiones separadas, una tras
otra**. Cada bloque es autocontenido: una sesión toma un bloque, lo implementa, marca
sus casillas, actualiza el "Log de sesiones" y para. La siguiente sesión lee este
archivo primero y sigue con el bloque pendiente.

- **Spec:** [docs/specs/2026-07-28-diarizacion-hablantes.md](../specs/2026-07-28-diarizacion-hablantes.md) (aprobado)
- **Plan:** [docs/plans/2026-07-28-diarizacion-hablantes.md](2026-07-28-diarizacion-hablantes.md)
- **Pendiente:** P10 en [docs/pendientes.md](../pendientes.md)

## Cómo retomar (leer al empezar cualquier sesión)

1. Lee este archivo y el plan. **No re-derives** decisiones ya cerradas en el spec.
2. Busca el primer bloque sin ✅ en el tablero de abajo. Ese es el tuyo.
3. Respeta el orden: un bloque no arranca hasta que el anterior esté ✅ (hay
   dependencias reales — ver plan §6).
4. Al terminar: corre `pytest` y `ruff check .`, marca las casillas, escribe una línea
   en el "Log de sesiones" y para. No sigas con el siguiente bloque en la misma sesión
   salvo que Kike lo pida.
5. Reglas del repo: rutas explícitas en `git add`, no commitear salvo que Kike lo pida.

## Regla de invariantes (aplica a todos los bloques)

- Todo local (1) · no editar el video (2) · degradar sin GPU (3) · core no importa GUI
  (4) · whisperx/token como setup con error claro (5).
- **Sin `--diarize`, el comportamiento debe quedar idéntico al actual.** Los tests de
  outputs vigentes son el candado: no se modifican, deben seguir pasando.

## Tablero de bloques

- [x] **Bloque A — Motor (core)** · tareas A1–A5
- [x] **Bloque B — CLI** · tarea B1
- [x] **Bloque C — Online** · tareas C1–C3
- [x] **Bloque D — GUI** · tareas D1–D2
- [x] **Bloque E — Dependencias y docs** · tareas E1–E2
- [x] **Bloque F — Tests** · tareas F1–F3 (F4 = verificación real, va en k-verify)

### Detalle por tarea (marcar al cerrar)

**A — Motor**
- [x] A1 `Segment.speaker` + `JobOptions.diarize`/`num_speakers` (`core/models.py`)
- [x] A2 Errores `DiarizationUnavailable` / `DiarizationSetupError` (`core/errors.py`)
- [x] A3 Módulo `core/diarize.py` (wrapper whisperX, import diferido, token HF)
- [x] A4 Salidas con etiqueta de hablante (`core/outputs.py`)
- [x] A5 Enrutar `pipeline._obtain_text` (diarize fuerza transcripción)

**B — CLI**
- [x] B1 `--diarize` + `--speakers` en `tae local` y `tae url` (`cli.py`)

**C — Online**
- [x] C1 `OnlineJobOptions.diarize`/`num_speakers` (`online/models.py`) — adelantada
  en Bloque B (el `url` de B1 la necesita para no reventar; ver Log)
- [x] C2 Enrutar `online/runner._obtain_text` (diarize ignora subs, diariza audio)
- [x] C3 Propagar `diarize`/`num_speakers` en `run_playlist`
- [ ] C2 Enrutar `online/runner._obtain_text`
- [ ] C3 Propagar `diarize`/`num_speakers` en `run_playlist`

**D — GUI**
- [x] D1 Checkbox "Identificar hablantes" + campo nº hablantes (`gui/app.py`)
- [x] D2 Cablear a `JobOptions` y `OnlineJobOptions` (`_start` / `_start_online`)

**E — Deps y docs**
- [x] E1 Extra opcional `diarize = ["whisperx"]` (`pyproject.toml`)
- [x] E2 Sección "Diarización de hablantes" con setup del token HF (`README.md`)

**F — Tests**
- [x] F1 Salidas con hablante (`tests/test_outputs.py`)
- [x] F2 Enrutado con monkeypatch, sin GPU/token (`tests/test_pipeline_media.py`)
- [x] F3 Invariantes: import diferido + core sin GUI (`tests/test_invariants.py`)

## Criterio de "terminado" global

Todos los bloques ✅, `pytest` en verde, `ruff` limpio, y el flujo sin `--diarize`
sin cambios de comportamiento. **F4 (k-verify) cerrado en verde** el 2026-07-28:
diarización real de 2 voces verificada end-to-end (ver Log). P10 completo.

## Log de sesiones

_(cada sesión añade una línea: fecha · bloque · resultado · pytest/ruff)_

- 2026-07-28 · planificación · spec + plan + este tracker creados. Nada de código aún.
- 2026-07-28 · Bloque A (motor) · A1–A5 implementados: `Segment.speaker`,
  `JobOptions.diarize/num_speakers`, errores de setup, `core/diarize.py` (wrapper
  whisperX con import diferido y token HF), salidas con prefijo de hablante y
  enrutado en `pipeline._obtain_text`. `ruff` limpio, `pytest` 79/79 (outputs sin
  tocar). Verificado: importar `core.diarize` no carga whisperx y core no importa gui.
  Commit `cc81b86`, push a main.
- 2026-07-28 · Bloque B (CLI) · B1: `--diarize` + `--speakers` en `tae local` y
  `tae url`, cableados a `JobOptions`/`OnlineJobOptions`. Se **adelantó C1** (campos
  en `OnlineJobOptions`) porque el `url` de B1 los necesita: el plan ordena B1 antes
  de C1, pero pasar el kwarg sin el campo hace `TypeError`; adelantar C1 evita
  commitear un comando roto. **Falta Bloque C real (C2 enrutado en `online/runner`,
  C3 propagación en playlist):** hoy `tae url --diarize` acepta la bandera pero el
  runner online aún no diariza (usa la transcripción de siempre). `ruff` limpio,
  `pytest` 79/79. `--help` de ambos muestra las flags.
- 2026-07-28 · Bloque C (online) · C2: `online/runner._obtain_text` enruta a
  `diarize.transcribe_and_diarize` cuando `opts.diarize` (ignora subs del creador,
  avisa). C3: `run_playlist` propaga `diarize`/`num_speakers` a cada `entry_opts`
  (un fallo de diarización en un video se clasifica sin abortar el lote, por el
  try/except existente). C1 ya venía del Bloque B. Import diferido intacto:
  `online.runner` no carga whisperx ni gui. `ruff` limpio, `pytest` 79/79.
- 2026-07-28 · Bloque D (GUI) · D1: checkbox `cb_diarize` ("Identificar hablantes")
  y `QSpinBox` `spin_speakers` ("Nº de hablantes", 0=Automatico) en el grupo
  Transcripcion, con QSS coherente y deshabilitados durante la corrida. D2: `_start`
  y `_start_online` pasan `diarize`/`num_speakers` a `JobOptions`/`OnlineJobOptions`
  (helper `_speakers_value`, 0→None). Invariante 4 verificado: importar `tae.gui.app`
  no carga whisperx. `ruff` limpio, `pytest` 79/79.
- 2026-07-28 · Bloque E (deps + docs) · E1: extra opcional
  `[project.optional-dependencies] diarize = ["whisperx>=3.1"]` en `pyproject.toml`
  (no toca las deps duras; `uv sync` sin el extra deja el proyecto como hoy). E2:
  sección "Diarización de hablantes" en `README.md` (setup: `uv sync --extra diarize`,
  aceptar términos pyannote, token HF en `HF_TOKEN`/`HUGGINGFACE_TOKEN`, nada a la
  nube en runtime), filas `--diarize`/`--speakers` en la tabla y "fuera de alcance"
  actualizado. `pyproject.toml` parsea, `ruff` limpio, `pytest` 79/79.
- 2026-07-28 · Bloque F (tests) · F1: salidas con hablante en `test_outputs.py`
  (prefijo en `.srt`/`.txt`, línea en blanco solo al cambiar, candado "sin speaker =
  igual"). F2: enrutado en `test_pipeline_media.py` con monkeypatch de
  `diarize.transcribe_and_diarize` (diarize→diarize no transcribe + salida con
  etiqueta; `--diarize` sin audio→`NoAudioTrack`; unit puro de `_obtain_text` que
  ignora subtítulos con diarize, sin ffmpeg/GPU/token). F3: invariantes en
  `test_invariants.py` (importar `core.diarize` no carga whisperx ni PySide6).
  `ruff` limpio, `pytest` **87/87** (+8). **Todos los bloques A–F ✅.** Falta solo
  F4 = verificación real con GPU + token HF, en `k-verify-after-changes`.
- 2026-07-28 · k-verify (F4) · Corrida real end-to-end en CPU con token HF y audio
  sintético de 2 voces (SAPI David/Zira). Resultado: **2 `SPEAKER_xx` coherentes**,
  cada voz a su etiqueta, `--speakers 2` respetado, `.srt`/`.txt` con formato del
  spec §5. También verificados en vivo: token ausente→`DiarizationSetupError`,
  video sin audio + `--diarize`→`NoAudioTrack`, regresión sin `--diarize`. La corrida
  destapó y se arreglaron **3 bugs** (todos en esta fase, no commiteados aún hasta
  cerrar verde):
    1. `detect_device()` medía CUDA de ctranslate2, no de torch → whisperX intentaba
       CUDA con torch CPU-only y reventaba con traceback. Fix: `_torch_device()`.
    2. `use_auth_token=` ya no existe en whisperX 3.4 (`TypeError`), y la heurística
       de términos lo tragaba como "falta token". Fix: constructor elige el kwarg por
       la firma; la heurística ya no mapea `TypeError`/errores de código.
    3. El default del stack es `speaker-diarization-community-1`, no el 3.1; el
       mensaje de setup nombraba modelos equivocados. Fix: mensaje genérico + adjunta
       la URL exacta del error crudo de pyannote; README apunta a community-1.
  Se añadieron 5 tests que blindan los 3 fixes (`tests/test_diarize.py`).
  `ruff` limpio, `pytest` **92/92**. **P10 listo end-to-end.**
