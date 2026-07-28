# Plan — Diarización de hablantes (Camino C: whisperX)

- **Fecha:** 2026-07-28
- **Spec de referencia:** [docs/specs/2026-07-28-diarizacion-hablantes.md](../specs/2026-07-28-diarizacion-hablantes.md) (aprobado)

## 1. Objetivo

Añadir diarización opt-in al motor: con `--diarize` (CLI local y url) o el checkbox
de la GUI, un pipeline whisperX transcribe + alinea + separa hablantes y las salidas
`.srt`/`.txt` prefijan cada intervención con `SPEAKER_00`. Sin el flag, el motor se
comporta idéntico a hoy.

## 2. Contexto del problema

Hoy el texto sale como un muro continuo sin distinguir quién habla; en terapias y
entrevistas eso obliga a reconstruir turnos a mano. whisperX integra transcripción,
alineación y diarización, así que es el camino con menos pegamento propio. Detalle y
decisiones cerradas en el spec (§4, §5, §7).

## 3. Decisiones técnicas que fija el spec (no re-derivar)

- **whisperX solo con `--diarize`.** Sin el flag, se usa `core/transcribe.py` actual
  (faster-whisper), intacto. No se unifica todo bajo whisperX.
- **`--diarize` fuerza transcripción del audio** e ignora subtítulos
  incrustados/del creador/auto (no traen identidad de voz), avisando.
- **Etiquetas genéricas** `SPEAKER_00/01…`. Renombrar y speaker-ID entre videos:
  fuera de V1.
- **Token HF + whisperX = dependencias de setup** (invariante 5): error claro, no
  traceback, si faltan.
- **Degradar sin GPU** (invariante 3), **core sin GUI** (invariante 4), **todo
  local** (invariante 1).

## 4. Diseño de la integración

- `Segment` gana `speaker: str | None = None` (default → todo el código actual y
  las salidas sin diarizar quedan igual).
- Nuevo módulo aislado `core/diarize.py` que envuelve whisperX. **Import diferido**
  de whisperx dentro de la función (como ya se hace con faster-whisper), para que
  importar `core` no arrastre torch/pyannote y no rompa el invariante 4 ni el
  arranque sin la dependencia instalada.
- whisperx entra como **extra opcional** en `pyproject.toml`
  (`[project.optional-dependencies] diarize`), no como dep dura: se instala solo si
  quieres diarizar; si no está y pides `--diarize`, error claro de setup.
- `pipeline.py` y `online/runner.py` enrutan a `diarize` en su `_obtain_text` cuando
  la opción está activa; el resto del flujo (audio, escritura, cancelación) no cambia.

## 5. Lista de tareas

### Bloque A — Motor (core)

**A1. `Segment.speaker`**
- Archivo: `src/tae/core/models.py`.
- Añadir `speaker: str | None = None` a `Segment` (dataclass frozen; campo con
  default, va al final).
- Añadir a `JobOptions`: `diarize: bool = False` y `num_speakers: int | None = None`.
- **Hecho:** el proyecto importa sin error; `Segment("a")` y `Segment(..., speaker="SPEAKER_00")` funcionan; los tests existentes de outputs siguen pasando sin tocarlos.

**A2. Errores de setup de diarización**
- Archivo: `src/tae/core/errors.py`.
- Añadir `DiarizationUnavailable(TaeError)` (whisperx no instalado) y
  `DiarizationSetupError(TaeError)` (token HF ausente o términos no aceptados), cada
  uno con mensaje accionable en español (qué instalar / dónde sacar el token gratis /
  qué variable de entorno poner).
- **Hecho:** ambas excepciones existen y heredan de `TaeError` (así CLI y GUI las
  muestran como mensaje, no como traceback).

**A3. Módulo `core/diarize.py`**
- Archivo nuevo: `src/tae/core/diarize.py`.
- Función `transcribe_and_diarize(audio, *, model, language, num_speakers=None, duration=None, on_progress=None, on_info=None, should_cancel=None) -> tuple[list[Segment], str | None]`.
- Import diferido de `whisperx`; si `ImportError` → `DiarizationUnavailable`.
- Token HF: leer de env (`HF_TOKEN` / `HUGGINGFACE_TOKEN`); si falta → `DiarizationSetupError`.
  Si whisperx/pyannote falla al descargar pesos por términos no aceptados, mapear a
  `DiarizationSetupError` con instrucciones (no dejar salir el error crudo).
- Reutilizar `transcribe.detect_device()` (cuda/float16 vs cpu/int8) y
  `transcribe._add_cuda_dll_dirs()` para las DLLs CUDA en Windows.
- Flujo whisperX: `load_model` → `transcribe` → `load_align_model` + `align` →
  `DiarizationPipeline` (pasar `num_speakers` si viene, si no autodetección) →
  `assign_word_speakers`. Convertir cada segmento resultante a
  `Segment(start, end, text.strip(), speaker=seg.get("speaker"))`.
- Progreso: whisperX no entrega segmentos en streaming; reportar por **etapas** vía
  `on_info`/`on_progress` en los cortes (transcribe ~0.5, align ~0.75, diarize/asignar
  ~1.0), no por segmento.
- Sin GPU: `on_info` avisa que la diarización en CPU será lenta; procede igual.
- Consultar `should_cancel` entre etapas y lanzar `Cancelled`.
- **Hecho:** con whisperx instalado + token, devuelve `Segment[]` con `speaker`
  poblado; sin whisperx lanza `DiarizationUnavailable`; sin token lanza
  `DiarizationSetupError`. (La corrida real con media queda para k-verify.)

**A4. Salidas con etiqueta de hablante**
- Archivo: `src/tae/core/outputs.py`.
- Helper `_line_text(seg)` → `f"{seg.speaker}: {seg.text.strip()}"` si `seg.speaker`,
  si no `seg.text.strip()`.
- `write_srt`: usar el helper en la línea de texto del bloque.
- `write_txt`: usar el helper y, cuando `seg.speaker` cambia respecto al anterior,
  insertar una línea en blanco (spec §5). Sin speakers, salida idéntica a hoy.
- **Hecho:** con speakers, `.srt`/`.txt` muestran `SPEAKER_00: …`; sin speakers los
  archivos son byte a byte iguales a los actuales (los tests de outputs vigentes lo
  garantizan sin modificarse).

**A5. Enrutar en `pipeline.py`**
- Archivo: `src/tae/core/pipeline.py`, función `_obtain_text`.
- `use_embedded = info_probe.has_subtitles and not options.force_transcribe and not options.diarize`.
- En la rama de transcripción: si `options.diarize`, llamar a
  `diarize.transcribe_and_diarize(...)` (pasando `num_speakers`); si no, la
  `transcribe.transcribe(...)` de siempre.
- Si `options.diarize` y no hay audio → `NoAudioTrack("no hay audio que diarizar")`.
- Si había subtítulos y se activó diarize, emitir `info(...)` avisando que se ignoran
  y se transcribe.
- **Hecho:** `tae local video --diarize` transcribe aunque haya subtítulos; sin el
  flag el árbol de decisión es exactamente el de hoy.

### Bloque B — CLI

**B1. Flags en `tae local` y `tae url`**
- Archivo: `src/tae/cli.py`.
- Añadir a ambos comandos: `--diarize` (bool, default False) y `--speakers` (int
  opcional, default None) con ayuda breve.
- `local`: pasar a `JobOptions`. `url`: pasar a `OnlineJobOptions`.
- **Hecho:** `tae local --help` y `tae url --help` muestran las dos opciones; se
  propagan a las options correctas.

### Bloque C — Online

**C1. Opciones online**
- Archivo: `src/tae/online/models.py`.
- Añadir a `OnlineJobOptions`: `diarize: bool = False`, `num_speakers: int | None = None`.
- **Hecho:** el campo existe y `run_playlist` lo copia al construir `entry_opts`
  (ver C3).

**C2. Enrutar en `online/runner.py`**
- Archivo: `src/tae/online/runner.py`, función `_obtain_text`.
- `use_sub = dl.subtitle_path is not None and not opts.force_transcribe and not opts.diarize`.
- En la rama de transcripción: si `opts.diarize`, usar
  `diarize.transcribe_and_diarize(...)`; si no, `transcribe.transcribe(...)`.
- **Hecho:** `tae url URL --diarize` ignora subtítulos del creador y diariza el audio.

**C3. Propagar en el lote**
- Archivo: `src/tae/online/runner.py`, `run_playlist` (construcción de `entry_opts`).
- Copiar `diarize` y `num_speakers` a cada `entry_opts` (hoy se copian campo a campo).
- **Hecho:** cada video de una playlist hereda `--diarize`; un fallo de diarización en
  un video se clasifica como fallo del lote sin abortar el resto (comportamiento
  actual del `try/except` del runner).

### Bloque D — GUI

**D1. Controles de diarización**
- Archivo: `src/tae/gui/app.py`.
- En el grupo "Transcripción": checkbox `self.cb_diarize` ("Identificar hablantes") y
  un campo numérico opcional `self.spin_speakers` ("Nº de hablantes", vacío =
  automático). Estilo coherente con el QSS existente.
- Deshabilitar los controles mientras corre (añadirlos a `_set_running`).
- **Hecho:** los controles aparecen y no rompen el layout con scroll actual.

**D2. Cablear a las options**
- Archivo: `src/tae/gui/app.py`, `_start` y `_start_online`.
- Pasar `diarize=self.cb_diarize.isChecked()` y `num_speakers=<valor o None>` a
  `JobOptions` (local) y `OnlineJobOptions` (online).
- **Hecho:** marcar el checkbox en la GUI produce salidas con etiquetas de hablante
  tanto en local como en URL.
- **Nota (invariante 4):** la GUI solo pasa banderas; toda la lógica de diarización
  vive en `core`. No importar `whisperx` desde la GUI.

### Bloque E — Dependencias y docs

**E1. Extra opcional en `pyproject.toml`**
- Archivo: `pyproject.toml`.
- Añadir `[project.optional-dependencies]` con `diarize = ["whisperx>=3.1"]` (ajustar
  versión a la disponible). No tocar las deps duras actuales.
- **Hecho:** `uv sync` sin el extra deja el proyecto como hoy; con el extra instala
  whisperx. Sin el extra, `--diarize` da error de setup claro (A2/A3), no traceback.

**E2. Documentar el setup del token HF**
- Archivo: `README.md` (sección nueva "Diarización de hablantes").
- Pasos: instalar el extra `diarize`, aceptar los términos del modelo pyannote en
  HuggingFace, crear token gratuito, exportarlo como variable de entorno. Dejar claro
  que en runtime nada sale a la nube (invariante 1).
- **Hecho:** el README explica cómo dejar la diarización operativa desde cero.

### Bloque F — Tests

**F1. Salidas con hablante** — `tests/test_outputs.py`
- Casos: `Segment` con `speaker` → prefijo correcto en `.srt` y `.txt`; cambio de
  hablante → línea en blanco en `.txt`; sin speaker → salida idéntica a la actual.
- **Hecho:** `pytest tests/test_outputs.py` pasa, incluidos los casos nuevos.

**F2. Enrutado de diarización** — `tests/test_pipeline_media.py` (o test nuevo)
- Monkeypatch de `diarize.transcribe_and_diarize` para no ejecutar whisperx real.
- Verificar: con `diarize=True` y subtítulos presentes → se transcribe/diariza (no se
  usa la rama embedded); con `diarize=True` y sin audio → `NoAudioTrack`.
- **Hecho:** el enrutado queda cubierto sin depender de GPU ni token.

**F3. Invariantes** — `tests/test_invariants.py`
- Confirmar que `import tae.core.diarize` **no** importa `whisperx` en tiempo de
  módulo (import diferido), y que `core` sigue sin importar nada de `gui`.
- **Hecho:** `pytest` completo en verde y `ruff` limpio.

**F4. Verificación real (para k-verify, no automatizable aquí)**
- Con GPU + token: un audio de 2 voces produce 2 `SPEAKER_xx` coherentes; `--speakers 2`
  respeta el número; sin token → mensaje de setup; sin GPU → corre lento con aviso.
- **Hecho:** se ejecuta en la fase k-verify-after-changes.

## 6. Orden de implementación

A1 → A2 → A3 → A4 → A5 → B1 → C1 → C2 → C3 → D1 → D2 → E1 → E2 → F1 → F2 → F3.
(A primero porque todo cuelga de `Segment.speaker` y del módulo `diarize`.)

## 7. Riesgos y notas

- **Peso de whisperx:** arrastra torch/pyannote (cientos de MB). Por eso es extra
  opcional y con import diferido; verificar que instalar el extra no rompe el entorno
  CUDA actual (nvidia-cublas/cudnn ya presentes).
- **Progreso poco granular:** whisperX no da streaming por segmento; la barra avanzará
  por etapas, no fluido. Aceptable para V1.
- **CPU muy lento:** pyannote en CPU es notablemente más lento que Whisper en CPU;
  el aviso debe ser explícito para que no parezca colgado.
