"""Target del subproceso que ejecuta el motor para la GUI (P12).

La GUI ya no corre el motor en un hilo, sino en un `multiprocessing.Process` cuyo
target es `run_engine`. Asi, "Cancelar" mata el proceso y corta de inmediato en
cualquier etapa, sin arriesgar el torch/CUDA del proceso de la interfaz.

Este modulo es deliberadamente *sin GUI*: importa `core`/`online`, nunca PySide6 ni
whisperx en tiempo de import (invariante 4 + arranque limpio). El puente en
`worker.py` traduce los mensajes de la cola a senales Qt.

Protocolo de mensajes puestos en la cola (tuplas):
- ("stage", str)        etapa legible
- ("info", str)         aviso legible (device, descarga de pesos, hint de runtime)
- ("progress", float)   fraccion 0..1
- ("item", pos, total, title)  avance por entrada de una playlist
- ("ok", JobResult|OnlineJobResult)   terminal: exito de un video
- ("batch", BatchReport)              terminal: exito de una playlist
- ("failed", str)                     terminal: error legible (sin traceback)

Todos los objetos de resultado son dataclasses picklables, asi que viajan por la
cola sin serializacion manual.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any


def run_engine(queue: Any, kind: str, options: Any, job_tmp: Path | str) -> None:
    """Ejecuta un trabajo del motor y reporta todo por `queue`.

    `kind`: "local" (video local) u "online" (URL/playlist). `options` es el
    `JobOptions`/`OnlineJobOptions` correspondiente. `job_tmp` es la carpeta donde el
    motor debe dejar sus temporales; el proceso padre la borra al terminar (matado o
    no), asi que aqui solo redirigimos `tempfile` hacia ella.
    """
    tempfile.tempdir = str(job_tmp)

    def stage(msg: str) -> None:
        queue.put(("stage", msg))

    def info(msg: str) -> None:
        queue.put(("info", msg))

    def progress(fraction: float) -> None:
        queue.put(("progress", float(fraction)))

    try:
        if kind == "local":
            from tae.core.pipeline import run as run_pipeline

            result = run_pipeline(
                options,
                on_stage=stage,
                on_info=info,
                on_progress=progress,
                should_cancel=None,
            )
            queue.put(("ok", result))
        elif kind == "online":
            _run_online(queue, options, stage, info, progress)
        else:
            queue.put(("failed", f"Tipo de trabajo desconocido: {kind}"))
    except Exception as exc:  # noqa: BLE001 - todo error se reporta legible, sin traceback
        from tae.core.errors import TaeError

        if isinstance(exc, TaeError):
            queue.put(("failed", str(exc)))
        else:
            queue.put(("failed", f"Error inesperado: {exc}"))


def _run_online(queue: Any, opts: Any, stage, info, progress) -> None:
    """Replica el flujo online (antes en `OnlineWorker.run`) dentro del subproceso.

    Import diferido de `tae.online`: el flujo local no debe cargar yt-dlp.
    """
    from tae.online.download import probe_url
    from tae.online.runner import run_playlist, run_url
    from tae.online.ytdlp_utils import JS_RUNTIME_HINT, ensure_ytdlp, find_js_runtime

    ensure_ytdlp()
    if find_js_runtime() is None:
        info(JS_RUNTIME_HINT)
    stage("Inspeccionando la URL...")
    url_info = probe_url(opts.url)
    if url_info.is_playlist:
        def on_item(pos: int, total: int, title: str) -> None:
            queue.put(("item", pos, total, title))

        report = run_playlist(
            opts,
            on_stage=stage,
            on_info=info,
            on_progress=progress,
            on_item=on_item,
            should_cancel=None,
        )
        queue.put(("batch", report))
    else:
        result = run_url(
            opts,
            on_stage=stage,
            on_info=info,
            on_progress=progress,
            should_cancel=None,
        )
        queue.put(("ok", result))
