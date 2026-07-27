"""Localizacion y verificacion de los binarios ffmpeg/ffprobe (invariante 5).

No se asume que esten: se buscan en el PATH y, si faltan, se lanza un error con
instrucciones claras en vez de reventar a mitad del proceso.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .errors import FfmpegNotFound

_INSTALL_HINT = (
    "Instala ffmpeg y asegurate de que este en el PATH. "
    "En Windows: `winget install Gyan.FFmpeg` o descarga desde https://ffmpeg.org. "
    "Cierra y reabre la terminal despues de instalar."
)


@dataclass(frozen=True)
class FfmpegPaths:
    ffmpeg: str
    ffprobe: str


def find_ffmpeg() -> FfmpegPaths | None:
    """Devuelve las rutas si ambos binarios estan, o None si falta alguno."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        return FfmpegPaths(ffmpeg=ffmpeg, ffprobe=ffprobe)
    return None


def ensure_ffmpeg() -> FfmpegPaths:
    """Igual que find_ffmpeg pero lanza FfmpegNotFound si falta algo."""
    paths = find_ffmpeg()
    if paths is None:
        missing = []
        if not shutil.which("ffmpeg"):
            missing.append("ffmpeg")
        if not shutil.which("ffprobe"):
            missing.append("ffprobe")
        raise FfmpegNotFound(f"No se encontro {' ni '.join(missing)}. {_INSTALL_HINT}")
    return paths


def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    """Corre un comando ocultando la ventana de consola en Windows."""
    creationflags = 0
    startupinfo = None
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )
