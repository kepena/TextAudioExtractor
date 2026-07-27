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
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont, QFontDatabase, QIcon
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.errors import TaeError, UnreadableVideo
from ..core.ffmpeg_utils import find_ffmpeg
from ..core.models import JobOptions, JobResult, ProbeResult
from ..core.probe import probe as probe_video
from .worker import OnlineWorker, PipelineWorker

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

# --- Marca Kaiketek ---
AZUL_TEK = "#0071ed"
AZUL_KAI = "#0573c0"
VERDE_TEK = "#6ad60a"
VERDE_KAI = "#03905d"
TURQUESA = "#5fd3c8"
GRIS_TEXTO = "#333333"
BLANCO = "#ffffff"
GRIS_CLARO = "#f4f6f8"
GRIS_BORDE = "#e2e6ea"

# Wordmark tricolor KAI/KE/TEK (solo sobre fondo claro, regla obligatoria de marca).
WORDMARK = (
    f'<span style="color:{AZUL_TEK};font-weight:800;letter-spacing:1px;">KAI</span>'
    f'<span style="color:{TURQUESA};font-weight:800;letter-spacing:1px;">KE</span>'
    f'<span style="color:{VERDE_TEK};font-weight:800;letter-spacing:1px;">TEK</span>'
)

# Carpeta de assets (svg) en formato posix para las url() del QSS.
ASSETS = (Path(__file__).parent / "assets").as_posix()


def _find_logo() -> str:
    """Ruta del logo real de Kaiketek si esta puesto; si no, el arbolito de respaldo."""
    base = Path(__file__).parent / "assets"
    for name in ("kaiketek-logo.png", "kaiketek-logo.svg", "tree.svg"):
        if (base / name).exists():
            return (base / name).as_posix()
    return (base / "tree.svg").as_posix()


LOGO = _find_logo()

STYLE = f"""
QWidget {{
    background: {BLANCO};
    color: {GRIS_TEXTO};
    font-family: "Poppins", "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}
QLabel {{ background: transparent; }}
QLabel#wordmarkFooter {{
    font-family: "Montserrat", "Segoe UI", sans-serif;
    font-size: 9pt;
}}
QLabel#poweredBy {{
    color: #9aa4ad;
    font-size: 8.5pt;
}}
QLabel#apptitle {{
    font-family: "Montserrat", "Segoe UI", sans-serif;
    font-size: 25pt;
    font-weight: 800;
    color: {GRIS_TEXTO};
}}
QLabel#subheader {{
    color: {AZUL_KAI};
    font-size: 10pt;
}}
QGroupBox {{
    border: 1px solid {GRIS_BORDE};
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    background: {GRIS_CLARO};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {AZUL_TEK};
    font-family: "Montserrat", "Segoe UI", sans-serif;
    font-weight: 700;
}}
QPushButton {{
    font-family: "Montserrat", "Segoe UI", sans-serif;
    font-weight: 700;
    background: {BLANCO};
    color: {AZUL_TEK};
    border: 1.5px solid {AZUL_TEK};
    border-radius: 8px;
    padding: 7px 16px;
}}
QPushButton:hover {{ background: #eaf3fe; }}
QPushButton:disabled {{ color: #a9b2ba; border-color: {GRIS_BORDE}; background: {GRIS_CLARO}; }}
QPushButton#primary {{
    background: {AZUL_TEK};
    color: {BLANCO};
    border: none;
    padding: 9px 22px;
}}
QPushButton#primary:hover {{ background: {AZUL_KAI}; }}
QPushButton#primary:disabled {{ background: #b6d4f5; color: {BLANCO}; }}
QLineEdit, QComboBox {{
    background: {BLANCO};
    border: 1.5px solid #cdd4da;
    border-radius: 8px;
    padding: 7px 10px;
}}
QComboBox:hover, QLineEdit:hover {{ border-color: {TURQUESA}; }}
QLineEdit:focus, QComboBox:focus {{ border: 1.5px solid {AZUL_TEK}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    border-left: 1px solid #e4e8ec;
}}
QComboBox::down-arrow {{ image: url({ASSETS}/chevron.svg); width: 12px; height: 12px; }}
QCheckBox {{ spacing: 9px; background: transparent; }}
QCheckBox::indicator {{
    width: 20px; height: 20px;
    border: 1.5px solid #cdd4da;
    border-radius: 6px;
    background: {BLANCO};
}}
QCheckBox::indicator:hover {{ border-color: {TURQUESA}; }}
QCheckBox::indicator:checked {{
    border: 1.5px solid {VERDE_KAI};
    background: #eefbe3;
    image: url({ASSETS}/check.svg);
}}
QProgressBar {{
    border: 1px solid {GRIS_BORDE};
    border-radius: 8px;
    background: {GRIS_CLARO};
    height: 20px;
    text-align: center;
    color: {GRIS_TEXTO};
}}
QProgressBar::chunk {{
    border-radius: 7px;
    background: {VERDE_TEK};
}}
"""


class DropFrame(QFrame):
    """Zona para arrastrar un video."""

    def __init__(self, on_file) -> None:
        super().__init__()
        self._on_file = on_file
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(90)
        self.setStyleSheet(
            f"DropFrame {{ border: 2px dashed {TURQUESA}; border-radius: 12px; "
            f"background: {GRIS_CLARO}; }}"
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
        self.setWindowIcon(QIcon(LOGO))
        self.setMinimumWidth(560)

        self._video: Path | None = None
        self._probe: ProbeResult | None = None
        self._worker: PipelineWorker | None = None
        self._last_out_dir: Path | None = None

        self._build_ui()
        self._check_ffmpeg()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        # El contenido vive en un widget interno dentro de un QScrollArea: asi la
        # ventana siempre cabe en la pantalla (se desplaza si es baja) y nunca deja
        # el pie por fuera. La ventana en si solo aloja el scroll.
        self.content = QWidget()
        root = QVBoxLayout(self.content)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(QIcon(f"{ASSETS}/appicon.svg").pixmap(44, 44))
        title_row.addWidget(self.icon_label)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title = QLabel("Text/Audio Extractor")
        title.setObjectName("apptitle")
        title_col.addWidget(title)
        subheader = QLabel("Extrae el texto y el audio de tus videos")
        subheader.setObjectName("subheader")
        title_col.addWidget(subheader)
        title_row.addLayout(title_col)
        title_row.addStretch()
        root.addLayout(title_row)

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

        # Online (URL de YouTube/plataformas)
        url_box = QGroupBox("O pega una URL (YouTube/online)")
        url_layout = QVBoxLayout(url_box)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…  ·  tambien playlists")
        self.url_edit.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self.url_edit)
        url_opts = QHBoxLayout()
        self.cb_auto_subs = QCheckBox("Aceptar subtitulos auto-generados")
        self.cb_keep = QCheckBox("Conservar la fuente descargada")
        url_opts.addWidget(self.cb_auto_subs)
        url_opts.addWidget(self.cb_keep)
        url_opts.addStretch()
        url_layout.addLayout(url_opts)
        cookies_row = QHBoxLayout()
        cookies_lbl = QLabel("Cookies (login/anti-bot):")
        self.cookies_edit = QLineEdit()
        self.cookies_edit.setPlaceholderText(
            "firefox / chrome / edge  ·  o ruta a un cookies.txt  ·  opcional"
        )
        self.cookies_edit.setToolTip(
            "Para videos que piden iniciar sesion o verificar que no eres un bot.\n"
            "Escribe el navegador donde tienes sesion en YouTube (ej. firefox), o la "
            "ruta a un archivo cookies.txt exportado. En Windows, Firefox es el mas "
            "fiable (Chrome/Edge cifran las cookies)."
        )
        cookies_row.addWidget(cookies_lbl)
        cookies_row.addWidget(self.cookies_edit)
        url_layout.addLayout(cookies_row)
        root.addWidget(url_box)

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
        self.start_btn.setObjectName("primary")
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

        # Footer "Powered by" — arbolito + KAIKETEK pequeño (marca en segundo plano)
        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.addStretch()
        powered = QLabel("Powered by")
        powered.setObjectName("poweredBy")
        footer.addWidget(powered)
        tree_lbl = QLabel()
        tree_lbl.setPixmap(QIcon(LOGO).pixmap(20, 20))
        footer.addWidget(tree_lbl)
        km = QLabel(WORDMARK)
        km.setObjectName("wordmarkFooter")
        km.setTextFormat(Qt.RichText)
        footer.addWidget(km)
        footer.addStretch()
        root.addSpacing(4)
        root.addLayout(footer)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

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
        self.open_btn.setEnabled(False)
        self.progress.setValue(0)
        self.stage_label.setText("")
        self._update_start_enabled()

    def _on_url_changed(self, text: str) -> None:
        """Al escribir una URL, sugiere una carpeta de salida si no hay ninguna."""
        if text.strip() and not self.out_edit.text().strip():
            self.out_edit.setText(str(Path.home() / "TextAudioExtractor"))
        self._update_start_enabled()

    def _update_start_enabled(self) -> None:
        has_source = self._video is not None or bool(self.url_edit.text().strip())
        running = self._worker is not None and self._worker.isRunning()
        self.start_btn.setEnabled(has_source and not running)

    def _pick_out_dir(self) -> None:
        start = self.out_edit.text() or ""
        path = QFileDialog.getExistingDirectory(self, "Carpeta de salida", start)
        if path:
            self.out_edit.setText(path)

    # ---------- Procesar ----------
    def _start(self) -> None:
        if not (self.cb_txt.isChecked() or self.cb_srt.isChecked() or self.cb_audio.isChecked()):
            QMessageBox.information(self, "Nada que generar", "Marca al menos una salida.")
            return
        # La URL tiene prioridad si el usuario escribio una.
        if self.url_edit.text().strip():
            self._start_online()
            return
        if not self._video:
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

    def _start_online(self) -> None:
        from ..online.models import OnlineJobOptions

        url = self.url_edit.text().strip()
        out_dir = Path(self.out_edit.text().strip() or (Path.home() / "TextAudioExtractor"))

        opts = OnlineJobOptions(
            url=url,
            out_dir=out_dir,
            want_txt=self.cb_txt.isChecked(),
            want_srt=self.cb_srt.isChecked(),
            want_audio=self.cb_audio.isChecked(),
            force_transcribe=self.cb_force.isChecked(),
            language=LANGUAGES[self.cmb_lang.currentIndex()][1],
            model=self.cmb_model.currentText(),
            allow_auto_subs=self.cb_auto_subs.isChecked(),
            keep_video=self.cb_keep.isChecked(),
            cookies=self.cookies_edit.text().strip() or None,
        )
        self._last_out_dir = out_dir

        self._worker = OnlineWorker(opts)
        self._worker.stage.connect(self._on_stage)
        self._worker.info.connect(self._on_info)
        self._worker.progress.connect(self._on_progress)
        self._worker.item.connect(self._on_item)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.finished_batch.connect(self._on_finished_batch)
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
        has_source = self._video is not None or bool(self.url_edit.text().strip())
        self.start_btn.setEnabled(not running and has_source)
        self.cancel_btn.setEnabled(running)
        self.pick_btn.setEnabled(not running)
        self.out_btn.setEnabled(not running)
        self.url_edit.setEnabled(not running)
        self.cookies_edit.setEnabled(not running)

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

    def _on_item(self, pos: int, total: int, title: str) -> None:
        self.stage_label.setText(f"[{pos}/{total}] {title}")
        self.progress.setValue(0)

    def _on_finished_batch(self, report: object) -> None:
        from ..online.runner import summarize_batch

        self._set_running(False)
        self.progress.setValue(100)
        ok = len(report.successes)
        fail = len(report.failures)
        self.stage_label.setText(f"Lote listo: {ok} ok, {fail} con fallo.")
        self.open_btn.setEnabled(ok > 0)
        box = QMessageBox(self)
        box.setWindowTitle("Lote terminado")
        box.setIcon(QMessageBox.Warning if fail else QMessageBox.Information)
        box.setText(summarize_batch(report))
        box.exec()

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


def _load_brand_fonts() -> None:
    """Registra Montserrat y Poppins empaquetadas, sin depender de que esten en el SO."""
    fonts_dir = Path(__file__).parent / "fonts"
    for ttf in ("Montserrat-VF.ttf", "Poppins-Light.ttf", "Poppins-Regular.ttf"):
        path = fonts_dir / ttf
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # base neutral para que el QSS mande, sin tema oscuro del SO
    _load_brand_fonts()
    app.setWindowIcon(QIcon(LOGO))
    app.setFont(QFont("Poppins", 10))
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    _place_window_top(window)
    window.raise_()
    window.activateWindow()
    return app.exec()


def _place_window_top(window: QWidget) -> None:
    """Ajusta el alto al area disponible y ancla la ventana arriba-centro.

    Con el contenido dentro de un QScrollArea, la ventana nunca necesita ser mas
    alta que la pantalla: si el contenido no cabe, se desplaza. Se corre despues
    de show() para que frameGeometry() (que incluye la barra de titulo) sea real.
    """
    screen = window.screen()
    if screen is None:
        return
    avail = screen.availableGeometry()
    margin = 16
    chrome = window.frameGeometry().height() - window.geometry().height()
    max_h = avail.height() - chrome - 2 * margin
    content_h = window.content.sizeHint().height() + 8
    height = max(360, min(content_h, max_h))
    width = max(window.width(), 620)
    window.resize(width, height)
    frame = window.frameGeometry()
    frame.moveTop(avail.top() + margin)
    frame.moveLeft(avail.left() + (avail.width() - frame.width()) // 2)
    window.move(frame.topLeft())


if __name__ == "__main__":
    sys.exit(main())
