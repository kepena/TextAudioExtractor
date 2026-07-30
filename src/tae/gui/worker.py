"""Puente entre la GUI y el motor, que corre en un subproceso (P12).

Antes cada worker ejecutaba el motor en su propio `QThread`; la cancelacion era
cooperativa (solo entre etapas), asi que en un archivo largo "Cancelar" tardaba
minutos. Ahora el `QThread` es solo un *puente*: lanza un `multiprocessing.Process`
(target `engine_process.run_engine`), lee sus mensajes de una cola y los re-emite
como senales Qt. "Cancelar" mata el proceso -> corte inmediato en cualquier etapa,
sin dejar el torch/CUDA del proceso de la GUI en mal estado.

`PipelineWorker`/`OnlineWorker` conservan su interfaz (`__init__(options)` + las
mismas senales), asi que `app.py` no cambia su cableado.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from queue import Empty

from PySide6.QtCore import QThread, Signal

from .engine_process import run_engine


class _EngineBridge(QThread):
    """Corre un trabajo del motor en un subproceso y reexpone su avance como senales.

    Las subclases fijan `_kind` ("local" u "online"). El motor real vive en
    `engine_process.run_engine`; aqui solo se traduce la cola a senales Qt.
    """

    stage = Signal(str)
    info = Signal(str)
    progress = Signal(float)
    item = Signal(int, int, str)       # pos, total, titulo (lote online)
    finished_ok = Signal(object)       # JobResult | OnlineJobResult
    finished_batch = Signal(object)    # BatchReport (playlist)
    failed = Signal(str)
    cancelled = Signal()

    _kind: str = ""

    def __init__(self, options: object) -> None:
        super().__init__()
        self._options = options
        self._cancel = False
        self._process = None

    def cancel(self) -> None:
        """Pide cancelar: mata el subproceso, cortando de inmediato."""
        self._cancel = True
        proc = self._process
        if proc is not None and proc.is_alive():
            proc.terminate()

    def run(self) -> None:  # ejecutado en el hilo puente
        from multiprocessing import Process, Queue

        queue: Queue = Queue()
        job_tmp = Path(tempfile.mkdtemp(prefix="tae_job_"))
        process = Process(
            target=run_engine,
            args=(queue, self._kind, self._options, job_tmp),
        )
        self._process = process

        terminal = False
        try:
            process.start()
            while True:
                try:
                    msg = queue.get(timeout=0.1)
                except Empty:
                    if not process.is_alive():
                        break
                    continue
                if self._dispatch(msg):
                    terminal = True
                    break

            if not terminal:
                # El proceso termino sin mensaje terminal: o lo matamos (cancelar)
                # o murio inesperadamente (crash).
                if self._cancel:
                    self.cancelled.emit()
                else:
                    self.failed.emit("El proceso del motor termino inesperadamente.")
        finally:
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            shutil.rmtree(job_tmp, ignore_errors=True)
            self._process = None

    def _dispatch(self, msg: tuple) -> bool:
        """Traduce un mensaje de la cola a su senal Qt. Devuelve True si es terminal.

        Metodo puro (sin proceso) para poder testear la traduccion aisladamente.
        """
        kind = msg[0]
        if kind == "stage":
            self.stage.emit(msg[1])
            return False
        if kind == "info":
            self.info.emit(msg[1])
            return False
        if kind == "progress":
            self.progress.emit(msg[1])
            return False
        if kind == "item":
            self.item.emit(msg[1], msg[2], msg[3])
            return False
        if kind == "ok":
            self.finished_ok.emit(msg[1])
            return True
        if kind == "batch":
            self.finished_batch.emit(msg[1])
            return True
        if kind == "failed":
            self.failed.emit(msg[1])
            return True
        # Mensaje desconocido: se ignora, no es terminal.
        return False


class PipelineWorker(_EngineBridge):
    """Flujo local (video en disco)."""

    _kind = "local"


class OnlineWorker(_EngineBridge):
    """Flujo online (URL/playlist). La decision playlist-vs-video y el import de
    `tae.online` ocurren dentro del subproceso (`engine_process`)."""

    _kind = "online"
