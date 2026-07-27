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


class OnlineWorker(QThread):
    """Corre el flujo online (URL) sin congelar la ventana.

    Import diferido de `tae.online` en `run()`: la GUI no arrastra el modulo
    online (ni yt-dlp) hasta que el usuario procesa una URL.
    """

    stage = Signal(str)
    info = Signal(str)
    progress = Signal(float)
    item = Signal(int, int, str)      # pos, total, titulo (lote)
    finished_ok = Signal(object)      # OnlineJobResult (video unico)
    finished_batch = Signal(object)   # BatchReport (playlist)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options: object) -> None:
        super().__init__()
        self._options = options
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _should_cancel(self) -> bool:
        return self._cancel

    def run(self) -> None:  # ejecutado en el hilo
        from ..online.download import probe_url
        from ..online.runner import run_playlist, run_url
        from ..online.ytdlp_utils import ensure_ytdlp

        try:
            ensure_ytdlp()
            self.stage.emit("Inspeccionando la URL...")
            url_info = probe_url(self._options.url)
            if url_info.is_playlist:
                report = run_playlist(
                    self._options,
                    on_stage=self.stage.emit,
                    on_info=self.info.emit,
                    on_progress=self.progress.emit,
                    on_item=lambda p, t, ti: self.item.emit(p, t, ti),
                    should_cancel=self._should_cancel,
                )
                self.finished_batch.emit(report)
            else:
                result = run_url(
                    self._options,
                    on_stage=self.stage.emit,
                    on_info=self.info.emit,
                    on_progress=self.progress.emit,
                    should_cancel=self._should_cancel,
                )
                self.finished_ok.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except TaeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # imprevisto: no matar la app
            self.failed.emit(f"Error inesperado: {exc}")
