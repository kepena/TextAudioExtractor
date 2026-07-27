"""Ventana principal de TextAudioExtractor (PySide6).

Cliente delgado: recoge las opciones del usuario, arranca el PipelineWorker y
muestra progreso/resultados. Toda la logica pesada vive en tae.core.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.errors import TaeError, UnreadableVideo
from ..core.ffmpeg_utils import find_ffmpeg
from ..core.models import JobOptions, JobResult, ProbeResult
from ..core.probe import probe as probe_video
from .worker import PipelineWorker

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".wmv"}
MODELS = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = [
    ("Automatico", None),
    ("Espanol (es)", "es"),
    ("Ingles (en)", "en"),
    ("Portugues (pt)", "pt"),
    ("Frances (fr)", "fr"),
    ("Aleman (de)", "de"),
    ("Italiano (it)", "it"),
]


class DropFrame(QFrame):
    """Zona para arrastrar un video."""

    def __init__(self, on_file) -> None:
        super().__init__()
        self._on_file = on_file
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(90)
        self.setStyleSheet(
            "DropFrame { border: 2px dashed #888; border-radius: 8px; }"
        )
        layout = QVBoxLayout(self)
        self.label = QLabel("Arrastra un video aqui  ·  o usa 'Elegir archivo'")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in VIDEO_EXTS:
                self._on_file(path)
                return
        QMessageBox.warning(self, "Formato no soportado", "Ese archivo no parece un video.")


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TextAudioExtractor")
        self.setMinimumWidth(560)

        self._video: Path | None = None
        self._probe: ProbeResult | None = None
        self._worker: PipelineWorker | None = None
        self._last_out_dir: Path | None = None

        self._build_ui()
        self._check_ffmpeg()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        self.drop = DropFrame(self._load_video)
        root.addWidget(self.drop)

        pick_row = QHBoxLayout()
        self.pick_btn = QPushButton("Elegir archivo…")
        self.pick_btn.clicked.connect(self._pick_file)
        pick_row.addWidget(self.pick_btn)
        pick_row.addStretch()
        root.addLayout(pick_row)

        self.info_label = QLabel("Ningun video cargado.")
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)

        # Salidas
        out_box = QGroupBox("Que quieres generar")
        out_layout = QHBoxLayout(out_box)
        self.cb_txt = QCheckBox("Texto plano (.txt)")
        self.cb_txt.setChecked(True)
        self.cb_srt = QCheckBox("Subtitulos (.srt)")
        self.cb_srt.setChecked(True)
        self.cb_audio = QCheckBox("Audio separado")
        out_layout.addWidget(self.cb_txt)
        out_layout.addWidget(self.cb_srt)
        out_layout.addWidget(self.cb_audio)
        root.addWidget(out_box)

        # Transcripcion
        tr_box = QGroupBox("Transcripcion (cuando no hay subtitulos)")
        grid = QGridLayout(tr_box)
        self.cb_force = QCheckBox("Transcribir de todos modos (ignorar subtitulos incrustados)")
        grid.addWidget(self.cb_force, 0, 0, 1, 2)
        grid.addWidget(QLabel("Idioma:"), 1, 0)
        self.cmb_lang = QComboBox()
        for label, _code in LANGUAGES:
            self.cmb_lang.addItem(label)
        grid.addWidget(self.cmb_lang, 1, 1)
        grid.addWidget(QLabel("Modelo:"), 2, 0)
        self.cmb_model = QComboBox()
        self.cmb_model.addItems(MODELS)
        self.cmb_model.setCurrentText("medium")
        grid.addWidget(self.cmb_model, 2, 1)
        root.addWidget(tr_box)

        # Carpeta de salida
        out_dir_box = QGroupBox("Carpeta de salida")
        odl = QHBoxLayout(out_dir_box)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Se define al cargar el video")
        self.out_btn = QPushButton("Cambiar…")
        self.out_btn.clicked.connect(self._pick_out_dir)
        odl.addWidget(self.out_edit)
        odl.addWidget(self.out_btn)
        root.addWidget(out_dir_box)

        # Progreso
        self.stage_label = QLabel("")
        root.addWidget(self.stage_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # Acciones
        actions = QHBoxLayout()
        self.start_btn = QPushButton("Iniciar")
        self.start_btn.clicked.connect(self._start)
        self.start_btn.setEnabled(False)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        self.open_btn = QPushButton("Abrir carpeta")
        self.open_btn.clicked.connect(self._open_out_dir)
        self.open_btn.setEnabled(False)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.cancel_btn)
        actions.addStretch()
        actions.addWidget(self.open_btn)
        root.addLayout(actions)

    def _check_ffmpeg(self) -> None:
        if find_ffmpeg() is None:
            QMessageBox.critical(
                self,
                "Falta ffmpeg",
                "No se encontro ffmpeg/ffprobe en el sistema. Instalalo y reinicia la app.\n\n"
                "Windows: `winget install Gyan.FFmpeg` o https://ffmpeg.org",
            )
            self.pick_btn.setEnabled(False)
            self.drop.setEnabled(False)

    # ---------- Cargar video ----------
    def _pick_file(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "Elegir video", "", f"Videos ({exts})")
        if path:
            self._load_video(Path(path))

    def _load_video(self, path: Path) -> None:
        try:
            self._probe = probe_video(path)
        except UnreadableVideo as exc:
            QMessageBox.warning(self, "No pude leer el video", str(exc))
            return
        except TaeError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return

        self._video = path
        mins, secs = divmod(int(self._probe.duration), 60)
        if self._probe.subtitle_tracks:
            langs = ", ".join(t.language or "desconocido" for t in self._probe.subtitle_tracks)
            subs = f"Si ({len(self._probe.subtitle_tracks)}: {langs})"
        else:
            subs = "No"
        audio = "Si" if self._probe.has_audio else "No"
        self.info_label.setText(
            f"<b>{path.name}</b><br>Duracion: {mins}:{secs:02d}  ·  "
            f"Subtitulos incrustados: {subs}  ·  Audio: {audio}"
        )
        default_out = path.parent / path.stem
        self.out_edit.setText(str(default_out))
        self.start_btn.setEnabled(True)
        self.open_btn.setEnabled(False)
        self.progress.setValue(0)
        self.stage_label.setText("")

    def _pick_out_dir(self) -> None:
        start = self.out_edit.text() or ""
        path = QFileDialog.getExistingDirectory(self, "Carpeta de salida", start)
        if path:
            self.out_edit.setText(path)

    # ---------- Procesar ----------
    def _start(self) -> None:
        if not self._video:
            return
        if not (self.cb_txt.isChecked() or self.cb_srt.isChecked() or self.cb_audio.isChecked()):
            QMessageBox.information(self, "Nada que generar", "Marca al menos una salida.")
            return
        out_dir = Path(self.out_edit.text().strip() or (self._video.parent / self._video.stem))

        options = JobOptions(
            video=self._video,
            out_dir=out_dir,
            want_txt=self.cb_txt.isChecked(),
            want_srt=self.cb_srt.isChecked(),
            want_audio=self.cb_audio.isChecked(),
            force_transcribe=self.cb_force.isChecked(),
            language=LANGUAGES[self.cmb_lang.currentIndex()][1],
            model=self.cmb_model.currentText(),
        )
        self._last_out_dir = out_dir

        self._worker = PipelineWorker(options)
        self._worker.stage.connect(self._on_stage)
        self._worker.info.connect(self._on_info)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)

        self._set_running(True)
        self.progress.setValue(0)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker:
            self.stage_label.setText("Cancelando…")
            self._worker.cancel()

    def _set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running and self._video is not None)
        self.cancel_btn.setEnabled(running)
        self.pick_btn.setEnabled(not running)
        self.out_btn.setEnabled(not running)

    # ---------- Señales del worker ----------
    def _on_stage(self, msg: str) -> None:
        self.stage_label.setText(msg)

    def _on_info(self, msg: str) -> None:
        self.stage_label.setText(msg)

    def _on_progress(self, fraction: float) -> None:
        self.progress.setValue(int(fraction * 100))

    def _on_finished(self, result: JobResult) -> None:
        self._set_running(False)
        self.progress.setValue(100)
        parts = []
        if result.txt_path:
            parts.append(".txt")
        if result.srt_path:
            parts.append(".srt")
        if result.audio_path:
            parts.append("audio")
        extra = f" · idioma {result.language}" if result.language else ""
        self.stage_label.setText(f"Listo: {', '.join(parts)}{extra}")
        self.open_btn.setEnabled(True)

    def _on_failed(self, msg: str) -> None:
        self._set_running(False)
        self.stage_label.setText("")
        QMessageBox.critical(self, "No se pudo completar", msg)

    def _on_cancelled(self) -> None:
        self._set_running(False)
        self.progress.setValue(0)
        self.stage_label.setText("Cancelado. No se generaron archivos validos.")

    def _open_out_dir(self) -> None:
        if not self._last_out_dir or not self._last_out_dir.exists():
            return
        path = str(self._last_out_dir)
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
