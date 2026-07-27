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

# Navegadores que yt-dlp entiende en `--cookies-from-browser`. Si el valor de
# cookies coincide con uno de estos (raiz antes de `+`/`:`), se pasa como
# navegador; si no, se asume ruta a un archivo cookies.txt (formato Netscape).
_KNOWN_BROWSERS = {
    "brave", "chrome", "chromium", "edge", "firefox",
    "opera", "safari", "vivaldi", "whale",
}

# Interpretes de JavaScript que yt-dlp puede usar para resolver el desafio
# `nsig`/PO-token de YouTube. Sin uno, YouTube estrangula o rechaza la descarga
# aunque las cookies sean validas.
_JS_RUNTIMES = ("deno", "node", "bun")

JS_RUNTIME_HINT = (
    "No encontre un runtime de JavaScript (deno/node) en el PATH. YouTube hoy lo "
    "exige para resolver su firma; sin el, las descargas pueden estrangularse o "
    "fallar aunque pases cookies. Recomendado: `winget install DenoLand.Deno` "
    "(o instala Node.js). Cierra y reabre la terminal despues."
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


def find_js_runtime() -> str | None:
    """Devuelve la ruta al primer runtime JS disponible (deno/node/bun), o None.

    No es un requisito duro (invariante 5: se avisa, no se revienta): muchas
    plataformas funcionan sin el; es YouTube quien lo necesita para su `nsig`.
    """
    for exe in _JS_RUNTIMES:
        path = shutil.which(exe)
        if path is not None:
            return path
    return None


def cookie_args(cookies: str | None) -> list[str]:
    """Traduce el campo `cookies` del usuario a args de yt-dlp.

    Un solo campo cubre los dos caminos (decision con Kike 2026-07-27):
    - nombre de navegador (`firefox`, `chrome:default`, ...) -> lee las cookies
      del navegador via `--cookies-from-browser`.
    - cualquier otra cosa (una ruta a `cookies.txt`) -> `--cookies FILE`.
    Vacio/None -> sin cookies.
    """
    if not cookies or not cookies.strip():
        return []
    spec = cookies.strip()
    # yt-dlp acepta BROWSER[+KEYRING][:PROFILE][::CONTAINER]; la raiz es lo que
    # decide si es navegador o archivo.
    root = spec.split("+", 1)[0].split(":", 1)[0].lower()
    if root in _KNOWN_BROWSERS:
        return ["--cookies-from-browser", spec]
    return ["--cookies", spec]


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
