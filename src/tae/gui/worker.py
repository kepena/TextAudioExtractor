"""Worker en hilo: corre pipeline.run sin congelar la ventana.

Reemite las etapas, avisos y progreso del motor como senales Qt. La cancelacion
es un flag que el pipeline consulta via should_cancel.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.errors import Cancelled, TaeError
from ..core.models import JobOptions, JobResult
from ..core.pipeline import run as run_pipeline


class PipelineWorker(QThread):
    stage = Signal(str)
    info = Signal(str)
    progress = Signal(float)
    finished_ok = Signal(object)   # JobResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options: JobOptions) -> None:
        super().__init__()
        self._options = options
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _should_cancel(self) -> bool:
        return self._cancel

    def run(self) -> None:  # ejecutado en el hilo
        try:
            result: JobResult = run_pipeline(
                self._options,
                on_stage=self.stage.emit,
                on_info=self.info.emit,
                on_progress=self.progress.emit,
                should_cancel=self._should_cancel,
            )
        except Cancelled:
            self.cancelled.emit()
        except TaeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # imprevisto: no matar la app
            self.failed.emit(f"Error inesperado: {exc}")
        else:
            self.finished_ok.emit(result)
