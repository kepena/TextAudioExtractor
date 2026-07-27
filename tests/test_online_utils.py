"""Fundaciones del modulo online: verificacion de yt-dlp (A1) y errores (A2)."""

import pytest

from tae.core.errors import TaeError
from tae.online.errors import (
    CAUSE_MESSAGES,
    DownloadFailed,
    FailureCause,
    YtDlpNotFound,
    message_for,
)
from tae.online.ytdlp_utils import (
    cookie_args,
    ensure_ytdlp,
    find_js_runtime,
    find_ytdlp,
)


def test_ytdlp_ausente_da_error_claro(monkeypatch):
    """Sin yt-dlp en PATH, ensure_ytdlp lanza un error accionable (invariante 5)."""
    monkeypatch.setattr("tae.online.ytdlp_utils.shutil.which", lambda _: None)
    assert find_ytdlp() is None
    with pytest.raises(YtDlpNotFound) as exc:
        ensure_ytdlp()
    msg = str(exc.value).lower()
    assert "yt-dlp" in msg
    assert "pip install -u yt-dlp" in msg


def test_ytdlp_presente_devuelve_ruta(monkeypatch):
    """Si yt-dlp esta en PATH, ensure_ytdlp devuelve su ruta."""
    monkeypatch.setattr(
        "tae.online.ytdlp_utils.shutil.which", lambda _: "/usr/bin/yt-dlp"
    )
    assert ensure_ytdlp() == "/usr/bin/yt-dlp"


def test_cada_causa_tiene_mensaje_accionable():
    """Cada FailureCause mapea a un mensaje en espanol (spec §6)."""
    for cause in FailureCause:
        assert cause in CAUSE_MESSAGES
        msg = message_for(cause)
        assert msg and isinstance(msg, str)


def test_errores_online_heredan_de_taeerror():
    """CLI/GUI muestran estos errores igual que los del motor (heredan TaeError)."""
    assert issubclass(YtDlpNotFound, TaeError)
    assert issubclass(DownloadFailed, TaeError)


def test_download_failed_lleva_causa_y_url():
    """DownloadFailed conserva la causa y la url para el resumen de lote."""
    err = DownloadFailed("boom", cause=FailureCause.PRIVATE, url="http://x")
    assert err.cause is FailureCause.PRIVATE
    assert err.url == "http://x"
    # Por defecto, causa UNKNOWN y sin url.
    default = DownloadFailed("boom")
    assert default.cause is FailureCause.UNKNOWN
    assert default.url is None


# ---------- cookie_args (P8) ----------
@pytest.mark.parametrize("value", [None, "", "   "])
def test_cookie_args_vacio_sin_args(value):
    """Sin cookies, no se agrega nada al comando."""
    assert cookie_args(value) == []


@pytest.mark.parametrize(
    "value,expected",
    [
        ("firefox", ["--cookies-from-browser", "firefox"]),
        ("Chrome", ["--cookies-from-browser", "Chrome"]),  # case-insensitive
        ("firefox:default", ["--cookies-from-browser", "firefox:default"]),
        ("chrome+gnomekeyring", ["--cookies-from-browser", "chrome+gnomekeyring"]),
        ("  edge  ", ["--cookies-from-browser", "edge"]),  # se recorta
    ],
)
def test_cookie_args_navegador(value, expected):
    """Un nombre de navegador conocido -> --cookies-from-browser (preserva el spec)."""
    assert cookie_args(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\kike\cookies.txt",
        "/home/kike/cookies.txt",
        "cookies.txt",
    ],
)
def test_cookie_args_archivo(value):
    """Cualquier cosa que no sea un navegador conocido -> --cookies FILE."""
    assert cookie_args(value) == ["--cookies", value]


# ---------- find_js_runtime (P8, deno/node) ----------
def test_find_js_runtime_presente(monkeypatch):
    """Devuelve la ruta del primer runtime JS disponible (deno primero)."""
    monkeypatch.setattr(
        "tae.online.ytdlp_utils.shutil.which",
        lambda exe: "/usr/bin/deno" if exe == "deno" else None,
    )
    assert find_js_runtime() == "/usr/bin/deno"


def test_find_js_runtime_ausente(monkeypatch):
    """Sin ningun runtime JS en PATH, devuelve None (se avisa, no se revienta)."""
    monkeypatch.setattr("tae.online.ytdlp_utils.shutil.which", lambda _: None)
    assert find_js_runtime() is None
