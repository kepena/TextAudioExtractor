# Plan — Diarización de hablantes en GPU vía WSL2

Fecha: 2026-07-30

## 1. Objetivo

Que la diarización de hablantes (P10) corra en la GPU (RTX 4050) cuando sea
posible, cruzando a WSL2/Ubuntu vía un subproceso `wsl.exe` en vez de correr en
CPU dentro de Windows como hoy. Todo lo demás (GUI, transcripción, extracción de
subtítulos/audio) sigue igual. Si el camino WSL2 no está disponible por cualquier
motivo, la app degrada automáticamente al camino CPU actual sin bloquear ni
reventar.

## 2. Contexto del Problema

`k2` (dependencia de `torchaudio` cuando detecta CUDA) no tiene ruedas para
Windows, así que la diarización quedó atada a CPU (~130 s para 28 s de audio →
horas para los videos reales de 1-2h de Kike, "no tolerable"). En Linux sí hay
ruedas de `k2`, y esta máquina ya tiene WSL2 (Ubuntu, WSL 2.6.1) con la GPU visible
dentro de esa distro (`nvidia-smi` confirmado). Detalle completo en P11
(`docs/pendientes.md`).

## 3. Spec de Referencia

`docs/specs/2026-07-30-diarizacion-gpu-wsl2.md` (aprobado 2026-07-30). Puntos que
condicionan las decisiones técnicas de este plan:
- §4 — solo la diarización cruza a WSL2; nada de mover GUI/transcripción, nada de
  servicio persistente, nada de instalar WSL2 (ya está instalado).
- §5 — detección automática de disponibilidad + degradación silenciosa a CPU; sin
  UI nueva para elegir GPU/CPU a mano; cancelar debe cortar de inmediato sin dejar
  cómputo huérfano en WSL2.
- §6 — cada modo de fallo (WSL2 ausente, entorno Ubuntu no configurado, `wsl.exe`
  colgado, carpeta compartida inaccesible, resultado corrupto) tiene su propio
  criterio de manejo, siempre sin traceback crudo.

## 4. Decisión de diseño: dónde vive el despacho GPU-vs-CPU

El spec original (brainstorm) sugería un módulo tipo `engine_process_wsl.py` del
lado GUI. Al revisar el código existente, ese lugar no es el correcto: `--diarize`
ya es una opción de la **CLI** (`tae local --diarize`), y el invariante 4
(`core` no depende de la GUI, debe poder correrse y probarse solo) implica que la
CLI también debería beneficiarse de GPU vía WSL2, no solo la GUI. Por eso la
bifurcación GPU-WSL2 vs CPU se implementa **dentro de `core`** (nuevo módulo
`core/diarize_wsl.py`, invocado desde `core/pipeline.py`), y no en `gui/`. La GUI
no cambia nada — sigue llamando `pipeline.run(...)` igual que hoy, y hereda el
comportamiento automáticamente a través del subproceso de P12.

## 5. Lista de Tareas a Implementar

### Bloque A — Entorno Ubuntu (setup, fuera del repo Python pero documentado)

**A1. Crear venv de diarización dentro de Ubuntu con whisperX 3.8 + torch cu128.**
- No es código del repo; es un venv en el filesystem de la distro (ruta fija y
  documentada, ej. `~/.venvs/tae-diarize`), instalado con
  `pip install torch --index-url .../cu128` + `pip install whisperx`.
- Archivos: ninguno en el repo todavía (ver A2 para el script que lo automatiza).
- Criterio de hecho: dentro de Ubuntu, `~/.venvs/tae-diarize/bin/python -c "import torch, whisperx; print(torch.cuda.is_available())"` imprime `True`.

**A2. Script de setup versionado en el repo (`scripts/wsl_diarize_setup.sh`).**
- Automatiza A1: crea el venv en la ruta fija, instala las dependencias, imprime
  instrucciones para exportar `HF_TOKEN`/`HUGGINGFACE_TOKEN` dentro de Ubuntu
  (mismo criterio que ya existe para Windows en `diarize.py`, pero del lado
  Linux — típicamente en `~/.bashrc` o un archivo `.env` que lea el script del
  worker de B1).
- Archivos: `scripts/wsl_diarize_setup.sh` (nuevo).
- Criterio de hecho: correr el script desde cero en la distro Ubuntu deja el venv
  operativo (mismo chequeo de A1) sin pasos manuales adicionales salvo pegar el
  token de HF.

### Bloque B — Script standalone que corre dentro de WSL2

**B1. `scripts/wsl_diarize_worker.py`: entrypoint que corre DENTRO del venv de Ubuntu.**
- Deliberadamente independiente del paquete `tae` (no se instala `tae` en Ubuntu,
  invariante de "solo cruza la diarización" — evita duplicar todo el entorno
  Windows del lado Linux). Reimplementa el flujo mínimo de
  `core/diarize.py::transcribe_and_diarize` (transcribe → align → diarize) usando
  whisperx directo, con los mismos 3 checkpoints de progreso (0.5/0.75/1.0).
- Entrada: argumentos de línea de comandos — ruta al audio (ya convertida a path
  Linux), modelo, idioma opcional, `--speakers N` opcional, ruta de salida JSON.
- Salida: escribe el resultado (lista de segmentos con `start`/`end`/`text`/
  `speaker`, más el idioma detectado) como JSON en la ruta indicada — **no** por
  stdout, para no arriesgar truncar/mezclar output binario de whisperX con datos.
- Progreso/avisos: imprime por stdout líneas con un prefijo simple y parseable,
  ej. `TAE_PROGRESS 0.5`, `TAE_INFO Cargando modelos...`, `TAE_PID <pid>` (esta
  última al arrancar, ver bloque E de cancelación). Nada más debe ir a stdout con
  ese prefijo, para que el lado Windows pueda leer línea por línea sin ambigüedad.
- Manejo de errores: mismo criterio que `diarize.py` (`_looks_like_terms_error`,
  mensajes de setup vs. errores de código) — reescribir la heurística mínima
  necesaria aquí mismo (no puede importar `core/errors.py`, vive en otro entorno
  Python). Al fallar, imprime `TAE_ERROR <categoria> <mensaje>` por stdout y
  termina con código de salida distinto de 0.
- Archivos: `scripts/wsl_diarize_worker.py` (nuevo).
- Criterio de hecho: ejecutado a mano dentro del venv de Ubuntu
  (`~/.venvs/tae-diarize/bin/python scripts/wsl_diarize_worker.py --audio /mnt/c/.../audio.wav --out /mnt/c/.../result.json`)
  sobre un audio de prueba con 2 voces, produce un `result.json` con segmentos y
  `speaker` poblado, y las líneas `TAE_PROGRESS`/`TAE_INFO` se ven por stdout.

### Bloque C — Puente Windows → WSL2 en `core`

**C1. `core/diarize_wsl.py::is_available() -> bool` (o similar).**
- Chequeo rápido y con timeout corto (pocos segundos) de que: `wsl.exe` existe en
  PATH, la distro configurada responde, el venv de diarización existe en la ruta
  esperada dentro de esa distro, y la GPU es visible ahí (ej.
  `wsl.exe -d <distro> -- <venv>/bin/python -c "import torch;print(torch.cuda.is_available())"`).
  Cualquier fallo (timeout, distro no encontrada, venv ausente, GPU no visible)
  devuelve `False` sin excepción — nunca bloquea.
- Distro configurable vía variable de entorno (`TAE_WSL_DISTRO`, default `"Ubuntu"`,
  coherente con lo ya confirmado en esta máquina); ruta del venv también
  configurable (`TAE_WSL_DIARIZE_VENV`, default a la ruta fija de A1/A2).
- Archivos: `src/tae/core/diarize_wsl.py` (nuevo).
- Criterio de hecho: test unitario con `subprocess` mockeado cubre los 4 casos
  (todo disponible → `True`; `wsl.exe` ausente, distro no responde, GPU no visible
  → `False` en cada uno), y en esta máquina real `is_available()` devuelve `True`
  una vez completado el Bloque A.

**C2. `core/diarize_wsl.py::transcribe_and_diarize_wsl(...)` — misma firma que `diarize.transcribe_and_diarize`.**
- Recibe los mismos parámetros que la función CPU (`audio`, `model`, `language`,
  `num_speakers`, `duration`, `on_progress`, `on_info`, `should_cancel`) y devuelve
  el mismo `tuple[list[Segment], str | None]`, para que `pipeline.py` pueda
  intercambiarlas sin lógica adicional.
- Traduce el path Windows del audio a un path visible por WSL2 usando
  `wsl.exe wslpath -a <path>` (soporta cualquier letra de unidad, no solo `C:` —
  relevante porque el repo vive en `G:\...`), en vez de asumir `/mnt/c` a mano.
- Lanza `wsl.exe -d <distro> -- <venv>/bin/python scripts/wsl_diarize_worker.py ...`
  con `subprocess.Popen` (stdout en modo texto, leído línea por línea en un loop no
  bloqueante o hilo lector), parsea las líneas `TAE_PROGRESS`/`TAE_INFO`/`TAE_ERROR`/
  `TAE_PID` y las traduce a `on_progress`/`on_info`/excepciones.
- Consulta `should_cancel()` periódicamente mientras el proceso corre (igual patrón
  que el resto del motor) y, si se pide cancelar, ejecuta la lógica del Bloque E
  para matar el árbol completo (Windows + WSL2), luego lanza `Cancelled`.
- Al terminar (éxito), lee el `result.json` de la carpeta compartida, lo convierte
  a `list[Segment]`, borra el JSON y el audio temporal de esa carpeta.
- Si el proceso `wsl.exe` termina con código ≠ 0 sin haber emitido `TAE_ERROR`
  reconocible, o el `result.json` no existe/está corrupto (JSON inválido, faltan
  campos): se trata como fallo del camino WSL2 — **no** se degrada a CPU
  silenciosamente aquí (eso ya se decidió antes de invocar este camino, en
  `is_available()`); se relanza como error claro de diarización.
- Archivos: `src/tae/core/diarize_wsl.py` (misma unidad que C1).
- Criterio de hecho: test de integración liviano (o manual, ver Bloque F) — sobre
  un audio real de 2 voces, `transcribe_and_diarize_wsl` devuelve segmentos con
  `speaker` poblado, en un tiempo comparable al de transcripción en GPU (no horas).

### Bloque D — Integración en el pipeline

**D1. Bifurcar en `core/pipeline.py::_obtain_text` (líneas ~135-146).**
- Donde hoy se llama directo `diarize.transcribe_and_diarize(...)`, insertar: si
  `diarize_wsl.is_available()` → usar `diarize_wsl.transcribe_and_diarize_wsl(...)`;
  si no → camino actual sin cambios (`diarize.transcribe_and_diarize(...)`, CPU).
- El aviso a `on_info` debe dejar explícito cuál camino se usó ("Diarizando en GPU
  vía WSL2" vs. el aviso ya existente de GPU/CPU local), para que quede
  trazable en los logs/UI de la GUI.
- Archivos: `src/tae/core/pipeline.py`.
- Criterio de hecho: con el Bloque A completo en esta máquina, correr
  `tae local <video> --diarize` usa el camino WSL2 (verificable por el mensaje de
  info y por el tiempo de ejecución); si se renombra temporalmente el venv de
  Ubuntu (simulando "no configurado"), la misma corrida cae a CPU sin error.

### Bloque E — Cancelación robusta (Windows + WSL2)

**E1. Matar el árbol completo al cancelar, no solo `wsl.exe`.**
- Riesgo concreto: `wsl.exe -d <distro> -- <comando>` es un proceso corto que
  reenvía la ejecución al init de la distro; matar el proceso `wsl.exe` en Windows
  (`Popen.terminate()`) no garantiza matar el proceso Python que quedó corriendo
  dentro de Ubuntu (mismo tipo de problema que P12 resolvió para el subproceso
  Windows, pero ahora cruzando la frontera de la VM de WSL2).
- Mitigación: capturar el PID real dentro de Ubuntu vía la línea `TAE_PID <pid>`
  que emite `wsl_diarize_worker.py` al arrancar (B1); al cancelar, además de matar
  el `Popen` de `wsl.exe`, ejecutar
  `wsl.exe -d <distro> -- kill -9 <pid>` para asegurar que el proceso dentro de la
  distro también muere.
- Esta lógica vive en `diarize_wsl.py` (invocada desde `should_cancel` dentro de
  C2), así que se activa igual para GUI (vía el subproceso de P12, que llama
  cancel → `should_cancel()` empieza a devolver `True`) y para CLI si algún día
  tiene cancelación.
- Archivos: `src/tae/core/diarize_wsl.py`.
- Criterio de hecho: cancelar desde la GUI a mitad de una diarización WSL2 dejar
  cero procesos Python huérfanos dentro de Ubuntu (verificable con
  `wsl.exe -d <distro> -- ps aux | grep wsl_diarize_worker` tras cancelar), corte
  en segundos (no minutos), sin salidas parciales en disco.

### Bloque F — Tests

**F1. Tests unitarios de `diarize_wsl.py` con `subprocess`/`Popen` mockeados.**
- Cubrir: `is_available()` en sus 4 variantes (Bloque C1); parseo de líneas
  `TAE_PROGRESS`/`TAE_INFO`/`TAE_ERROR`/`TAE_PID`; manejo de `result.json` ausente
  o corrupto; camino de cancelación (E1) sin depender de WSL2 real.
- Archivos: `tests/test_diarize_wsl.py` (nuevo).
- Criterio de hecho: `pytest` verde, cobertura de los casos de error del spec §6
  sin necesitar WSL2 instalado en la máquina que corre CI/tests.

**F2. Test de integración real (manual, no CI) sobre esta máquina.**
- Correr `tae local <video con 2 voces> --diarize` end-to-end con el Bloque A
  completo, confirmar 2 `SPEAKER_xx` coherentes y tiempo de proceso en el orden de
  minutos (no horas). Repetir cancelando a mitad.
- No es un test automatizado — es parte de `k-verify-after-changes` al cerrar este
  plan, pero se anota aquí porque es el criterio de aceptación real de todo el
  plan (spec §3: "no tolerable" en CPU).

### Bloque G — Documentación

**G1. Actualizar `docs/pendientes.md` (P11) y `docs/roadmap.md` (Fase 5) al cerrar.**
- Reemplazar el estado "⛔ bloqueado" de P11 por el resultado real una vez
  verificado, con el mismo nivel de detalle que las entradas ya cerradas.
- Archivos: `docs/pendientes.md`, `docs/roadmap.md`.
- Criterio de hecho: ambos documentos reflejan el estado final (GPU vía WSL2
  funcionando, o lo que realmente haya resultado de la verificación) sin dejar el
  brainstorm/plan como última palabra.

---

Plan guardado en `docs/plans/2026-07-30-diarizacion-gpu-wsl2.md`. Cuando se
implemente, usa `k-verify-after-changes` contra este plan y contra el spec de
referencia (§5 y §6 en particular, por los casos de degradación y cancelación).
