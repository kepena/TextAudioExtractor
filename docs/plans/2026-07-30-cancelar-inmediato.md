# Plan — Cancelar inmediato (P12)

- **Fecha:** 2026-07-30
- **Spec de referencia:** [docs/specs/2026-07-30-cancelar-inmediato.md](../specs/2026-07-30-cancelar-inmediato.md) (aprobado)

## 1. Objetivo

Que el botón **Cancelar** de la GUI detenga cualquier corrida del motor en ≤ ~2 s, en
cualquier etapa. Para eso, la GUI ejecuta el trabajo del motor en un **subproceso**
que mata al cancelar, en vez de un hilo que solo puede pedir cancelación cooperativa
entre etapas.

## 2. Contexto del problema

Las llamadas de whisperX (transcribir/alinear/diarizar) son nativas y monolíticas;
Python no las interrumpe desde dentro. Hoy `should_cancel` solo se consulta entre
etapas, así que en un archivo largo "Cancelar" queda pendiente minutos y la app parece
colgada (visto con un video de 84 min). Matar un subproceso corta de inmediato y no
deja el torch/CUDA del proceso de la GUI en mal estado. Detalle en el spec.

## 3. Spec de referencia

[docs/specs/2026-07-30-cancelar-inmediato.md](../specs/2026-07-30-cancelar-inmediato.md).
Decisiones cerradas relevantes: **GUI solo** (la CLI no se toca), **cubre todos los
jobs** (local + online, transcribir + diarizar), **cerrar la ventana cancela**. Casos
de §6 (subproceso muere solo, carrera al terminar, temporales huérfanos, GPU liberada,
cierre de ventana, reintento) son los que guían las tareas de manejo de errores.

## 4. Diseño técnico

- **Módulo nuevo `tae/gui/engine_process.py`** con una función a nivel de módulo
  `run_engine(queue, kind, options, job_tmp)` — es el *target* del subproceso.
  Importable, sin GUI (respeta invariante 4: importa `core`/`online`, nunca `gui`
  ni whisperx en tiempo de import).
- **La GUI corre el motor con `multiprocessing.Process`** (start method `spawn` en
  Windows). El subproceso no puede emitir señales Qt: manda mensajes por una
  `multiprocessing.Queue`.
- **El `QThread` deja de ejecutar el motor y pasa a ser un puente ("bridge")**: lanza
  el proceso, lee la cola en bucle y **re-emite las señales Qt existentes**
  (`stage/info/progress/item/finished_ok/finished_batch/failed/cancelled`). Así
  `app.py` casi no cambia: sigue conectando las mismas señales.
- **Cancelar = `process.terminate()`**. El bridge distingue *cancelado por el usuario*
  (flag puesto) de *muerte inesperada del proceso* (crash → `failed`).
- **Temporales:** el subproceso fija `tempfile.tempdir = job_tmp` al arrancar, así todo
  `TemporaryDirectory()`/`mkdtemp` del motor cae en esa carpeta; el bridge borra
  `job_tmp` al terminar (normal o matado). El `core` no se toca.
- **`should_cancel`:** ya no hace falta para cancelar (se mata el proceso). Se pasa
  `None`; el corte cooperativo entre etapas queda como estaba pero deja de ser el
  mecanismo principal.

### Protocolo de mensajes en la cola

Tuplas `(tipo, *datos)`:
- `("stage", str)` · `("info", str)` · `("progress", float)` · `("item", pos, total, title)`
- Terminales: `("ok", JobResult|OnlineJobResult)` · `("batch", BatchReport)` · `("failed", str)`

Todos los objetos de resultado (`JobResult`, `OnlineJobResult`, `BatchReport`,
`BatchFailure`, `Segment`, enums, `Path`) son dataclasses picklables → viajan por la
cola sin trabajo extra.

## 5. Lista de tareas

### Bloque A — Subproceso del motor

**A1. Módulo `engine_process.py` con el target `run_engine`**
- Archivo nuevo: `src/tae/gui/engine_process.py`.
- `run_engine(queue, kind, options, job_tmp)`:
  - `import tempfile; tempfile.tempdir = str(job_tmp)`.
  - Construye callbacks que hacen `queue.put(("stage", msg))`, etc.
  - Según `kind`:
    - `"local"` → `pipeline.run(options, on_stage=..., on_info=..., on_progress=..., should_cancel=None)` → `queue.put(("ok", result))`.
    - `"online"` → replica la lógica actual de `OnlineWorker.run` (ensure_ytdlp,
      find_js_runtime→info, `probe_url`; si playlist → `run_playlist` con `on_item` →
      `("batch", report)`; si no → `run_url` → `("ok", result)`).
  - `except TaeError as e: queue.put(("failed", str(e)))`;
    `except Exception as e: queue.put(("failed", f"Error inesperado: {e}"))`.
- **Import diferido de `tae.online`** dentro de la rama online (no cargar yt-dlp en el
  flujo local; mantener invariante del online aislado).
- **Hecho:** `import tae.gui.engine_process` no importa PySide6 ni whisperx; llamar
  `run_engine` con un `pipeline.run` monkeypatcheado deja los mensajes esperados en una
  `Queue` real.

### Bloque B — Puente en el worker (QThread)

**B1. Clase base `_EngineBridge(QThread)`**
- Archivo: `src/tae/gui/worker.py`.
- Señales: las actuales (`stage, info, progress, item, finished_ok, finished_batch,
  failed, cancelled`).
- `run()`: crea `Queue` y `job_tmp = Path(mkdtemp())`; lanza
  `Process(target=run_engine, args=(queue, kind, options, job_tmp))`; bucle:
  `queue.get(timeout=0.1)`; traduce cada mensaje a la señal Qt correspondiente;
  en terminal (`ok`/`batch`/`failed`) marca fin. Si `queue` vacía y
  `not process.is_alive()`: si `self._cancel` → `cancelled.emit()`, si no →
  `failed.emit("El proceso del motor terminó inesperadamente.")`.
  `finally`: `process.join(timeout)`, y `shutil.rmtree(job_tmp, ignore_errors=True)`.
- `cancel()`: `self._cancel = True; if process: process.terminate()`.
- **Hecho:** el bucle traduce todos los tipos de mensaje a su señal; matar el proceso
  emite `cancelled` (no `failed`); una muerte sin flag emite `failed`.

**B2. `PipelineWorker` y `OnlineWorker` como subclases delgadas**
- `PipelineWorker(_EngineBridge)` con `kind="local"`; `OnlineWorker(_EngineBridge)`
  con `kind="online"`. Ambos reciben `options` y ya no ejecutan el motor directamente.
- Quitar de `OnlineWorker.run` el `probe_url`/dispatch (se movió a `engine_process`).
- **Hecho:** `app.py` sigue instanciando `PipelineWorker(options)` /
  `OnlineWorker(opts)` y conectando las mismas señales, sin cambios de firma.

**B3. Distinguir cancelación de fin en la carrera (spec §6)**
- Si llega un terminal (`ok`/`batch`) **y** casi a la vez `cancel()`: gana lo que ya
  esté en la cola; si el terminal llegó, se completa (muestra "Listo"); si no, se
  cancela. Nunca ambos.
- **Hecho:** cancelar justo al terminar no deja la UI en estado ambiguo ni emite dos
  señales terminales.

### Bloque C — Arranque y cierre de la GUI

**C1. `multiprocessing` seguro en Windows (no romper el arranque)**
- Archivo: `src/tae/gui/app.py` (`main`) y el entry `tae-gui`.
- Llamar `multiprocessing.freeze_support()` y fijar el start method `spawn` una sola
  vez al inicio de `main()`, antes de crear la `QApplication`.
- Verificar que el hijo (spawn) **no relanza la GUI**: el target vive en
  `engine_process` (sin GUI) y el módulo de entrada no ejecuta `main()` en import.
- **Hecho (criterio de "no romper lo existente"):** lanzar `tae-gui`, correr un job y
  cancelarlo **no** abre una segunda ventana ni deja procesos huérfanos; una corrida
  normal (sin cancelar) termina y muestra "Listo" igual que hoy.

**C2. `closeEvent` cancela la corrida activa**
- Archivo: `src/tae/gui/app.py` (`MainWindow`).
- `closeEvent`: si hay worker corriendo, llamar `cancel()` (mata el subproceso) y
  aceptar el cierre; sin diálogo extra (decisión 3 del spec).
- **Hecho:** cerrar la ventana con una corrida activa termina el subproceso; no queda
  ningún proceso del motor trabajando en segundo plano.

### Bloque D — Tests

**D1. Traducción mensaje→señal del bridge (sin proceso real)**
- Archivo: `tests/test_gui_bridge.py` (nuevo).
- Refactor mínimo para testear: extraer el "traductor" de un mensaje a señal en un
  método puro `_dispatch(msg)` del bridge, y probarlo con una lista de mensajes,
  afirmando las señales/estados resultantes (sin `Process` real, con una `Queue`
  alimentada a mano o llamando `_dispatch` directo).
- **Hecho:** cada tipo de mensaje produce la señal correcta; un terminal marca fin.

**D2. Terminar un subproceso real ≤ ~2 s**
- Archivo: `tests/test_gui_bridge.py`.
- Target dummy que hace `time.sleep(30)` publicando algún `progress`; lanzarlo,
  `terminate()`, afirmar que el proceso muere en < 2 s y que se emite `cancelled`,
  y que `job_tmp` se borra.
- **Hecho:** el corte real cumple el objetivo de tiempo y limpia temporales.

**D3. `run_engine` publica el flujo correcto (motor monkeypatcheado)**
- Archivo: `tests/test_engine_process.py` (nuevo).
- Monkeypatch de `pipeline.run` para emitir un par de `stage/progress` y devolver un
  `JobResult`; correr `run_engine` con `kind="local"` y una `Queue` real; afirmar la
  secuencia de mensajes incluyendo `("ok", result)`. Igual para un `TaeError` →
  `("failed", ...)`.
- **Hecho:** el protocolo de cola queda cubierto sin GPU/token.

**D4. Invariantes**
- Archivo: `tests/test_invariants.py`.
- `import tae.gui.engine_process` no importa `PySide6` ni `whisperx` en tiempo de
  módulo; `core` sigue sin importar `gui`.
- **Hecho:** `pytest` completo en verde, `ruff` limpio.

### Bloque E — Docs

**E1. Cerrar P12 en el tracker de pendientes**
- Archivo: `docs/pendientes.md`.
- Al terminar la implementación y la verificación, marcar P12 con el resumen.
- **Hecho:** P12 refleja el estado real (implementado + verificado).

## 6. Orden de implementación

A1 → B1 → B2 → B3 → C1 → C2 → D1 → D2 → D3 → D4. (El motor-en-proceso primero, luego
el puente que lo consume, luego arranque/cierre, luego tests.)

## 7. Riesgos y notas

- **spawn en Windows es el punto delicado.** Si el módulo de entrada ejecutara la GUI
  en import, el hijo abriría otra ventana. Mitigación: target en módulo sin GUI +
  `freeze_support()` + guardas de entrada. C1 tiene criterio explícito de no-regresión.
- **Overhead de arranque del subproceso** (spawn reimporta): ~1-2 s extra al iniciar
  cada job. Aceptable frente a los minutos de una diarización; se puede mencionar en el
  log de etapas ("Preparando…") si molesta.
- **Interrumpir una descarga de pesos** (primera vez) deja temporales de
  `huggingface_hub`, que son reanudables; `job_tmp` cubre los del motor, no la caché HF
  (esa se queda, es intencional para no re-descargar). No es fuga real.
- **Verificación final (k-verify):** cancelar a mitad de una diarización larga corta en
  ≤ ~2 s; cerrar la ventana mata el subproceso; una corrida normal sigue dando "Listo";
  reintentar tras cancelar arranca limpio.
