"""Transcripcion local con faster-whisper.

- Usa GPU (CUDA) si esta disponible; si no, cae a CPU con aviso (invariante 3).
- En Windows agrega al PATH de DLLs las librerias CUDA que instala pip
  (nvidia-cublas-cu12 / nvidia-cudnn-cu12), para que CTranslate2 las encuentre.
- Entrega los segmentos en streaming y reporta progreso con seg.end / duracion.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from .models import Segment

_dll_dirs_added = False


def _add_cuda_dll_dirs() -> None:
    """En Windows, registra las carpetas de DLLs CUDA de los paquetes pip."""
    global _dll_dirs_added
    if _dll_dirs_added or sys.platform != "win32":
        return
    try:
        import nvidia  # noqa: F401
    except ImportError:
        _dll_dirs_added = True
        return
    for pkg in ("cublas", "cudnn"):
        for base in _site_nvidia_bins(pkg):
            if base.is_dir():
                os.add_dll_directory(str(base))
    _dll_dirs_added = True


def _site_nvidia_bins(pkg: str):
    import site

    roots = list(site.getsitepackages())
    user = site.getusersitepackages()
    if user:
        roots.append(user)
    for root in roots:
        yield Path(root) / "nvidia" / pkg / "bin"


def detect_device() -> tuple[str, str]:
    """Devuelve (device, compute_type). 'cuda'/'float16' si hay GPU, si no 'cpu'/'int8'."""
    _add_cuda_dll_dirs()
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def transcribe(
    audio: Path,
    *,
    model: str = "medium",
    language: str | None = None,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    on_info: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[Segment], str | None]:
    """Transcribe el audio. Devuelve (segmentos, idioma_detectado).

    `on_info` recibe avisos legibles (device usado, descarga de modelo).
    `should_cancel` se consulta entre segmentos para cortar limpio.
    """
    from faster_whisper import WhisperModel

    device, compute_type = detect_device()
    if on_info:
        if device == "cuda":
            on_info(f"Transcribiendo en GPU (modelo {model}).")
        else:
            on_info(
                f"No se detecto GPU NVIDIA disponible: se usara CPU (modelo {model}), "
                "sera mas lento."
            )
        on_info("Cargando el modelo (la primera vez con un modelo nuevo se descarga)...")

    whisper = WhisperModel(model, device=device, compute_type=compute_type)

    segment_iter, info = whisper.transcribe(
        str(audio),
        language=language,
        beam_size=5,
        vad_filter=True,
    )
    detected_language = getattr(info, "language", None) or language
    total = duration or getattr(info, "duration", 0.0) or 0.0

    segments: list[Segment] = []
    for seg in segment_iter:
        if should_cancel and should_cancel():
            from .errors import Cancelled

            raise Cancelled("Transcripcion cancelada por el usuario.")
        segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
        if on_progress and total > 0:
            on_progress(min(seg.end / total, 1.0))

    if on_progress:
        on_progress(1.0)
    return segments, detected_language
