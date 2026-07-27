"""Localizacion y verificacion del binario yt-dlp (invariante 5).

Espejo de `core/ffmpeg_utils.py`: yt-dlp es un binario del sistema, no una
dependencia pip (decision con Kike 2026-07-27), asi el usuario lo actualiza con
`pip install -U yt-dlp` cuando una plataforma rompe un extractor, sin esperar a
un release de tae. Si falta, se lanza un error accionable en vez de reventar a
mitad del proceso.
"""

from __future__ import annotations

import shutil
import subprocess

from .errors import YtDlpNotFound

_INSTALL_HINT = (
    "Instala yt-dlp y asegurate de que este en el PATH. "
    "Recomendado: `pip install -U yt-dlp` (tambien sirve para actualizarlo cuando "
    "YouTube rompe un extractor). En Windows tambien: `winget install yt-dlp.yt-dlp`. "
    "Cierra y reabre la terminal despues de instalar."
)


def find_ytdlp() -> str | None:
    """Devuelve la ruta a yt-dlp si esta en el PATH, o None si falta."""
    return shutil.which("yt-dlp")


def ensure_ytdlp() -> str:
    """Igual que find_ytdlp pero lanza YtDlpNotFound si falta."""
    path = find_ytdlp()
    if path is None:
        raise YtDlpNotFound(f"No se encontro yt-dlp. {_INSTALL_HINT}")
    return path


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
