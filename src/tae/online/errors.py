"""Errores tipados del modulo online (spec §6).

Heredan de `core.errors.TaeError` para que CLI y GUI los muestren igual que los
del motor (mensaje accionable, sin traceback). `DownloadFailed` lleva una
`FailureCause` para clasificar el fallo y armar el resumen del lote (spec §5.2).
"""

from __future__ import annotations

from enum import StrEnum

from tae.core.errors import TaeError


class FailureCause(StrEnum):
    """Causa clasificada de un fallo de descarga (para el resumen de lote)."""

    PRIVATE = "private"
    GEOBLOCKED = "geoblocked"
    UNAVAILABLE = "unavailable"
    NEEDS_LOGIN = "needs_login"
    COOKIES_ERROR = "cookies_error"
    EXTRACTOR_ERROR = "extractor_error"
    NETWORK = "network"
    UNKNOWN = "unknown"


# Mensaje accionable en espanol por cada causa (spec §6).
CAUSE_MESSAGES: dict[FailureCause, str] = {
    FailureCause.PRIVATE: (
        "El video es privado: el creador no lo comparte publicamente, no hay forma "
        "de descargarlo."
    ),
    FailureCause.GEOBLOCKED: (
        "El video esta bloqueado en tu region. Podrias necesitar una VPN para "
        "acceder a el."
    ),
    FailureCause.UNAVAILABLE: (
        "El video ya no existe o fue borrado por el creador o la plataforma."
    ),
    FailureCause.NEEDS_LOGIN: (
        "El video requiere iniciar sesion, confirmar edad o pasar la verificacion "
        "anti-bot. Indica cookies en el campo 'Cookies' (nombre de tu navegador con "
        "sesion en YouTube, ej. firefox, o la ruta a un cookies.txt) y reintenta."
    ),
    FailureCause.COOKIES_ERROR: (
        "No pude leer las cookies del navegador. En Windows, Chrome y Edge las cifran "
        "y suelen fallar (aunque cierres el navegador). Solucion: exporta un "
        "cookies.txt con una extension (ej. 'Get cookies.txt LOCALLY') e indica su "
        "ruta en el campo 'Cookies' en vez del nombre del navegador."
    ),
    FailureCause.EXTRACTOR_ERROR: (
        "yt-dlp no pudo procesar esta URL. Suele ser por yt-dlp desactualizado "
        "(actualizalo con `pip install -U yt-dlp`) o, en YouTube, por falta de un "
        "runtime de JavaScript (instala deno: `winget install DenoLand.Deno`)."
    ),
    FailureCause.NETWORK: (
        "Fallo la conexion de red al intentar descargar. Revisa tu internet e "
        "intentalo de nuevo."
    ),
    FailureCause.UNKNOWN: (
        "La descarga fallo por una causa no identificada. Revisa la URL e intentalo "
        "de nuevo."
    ),
}


def message_for(cause: FailureCause) -> str:
    """Devuelve el mensaje accionable en espanol para una causa."""
    return CAUSE_MESSAGES[cause]


class YtDlpNotFound(TaeError):
    """No se encontro el binario yt-dlp en el sistema (invariante 5)."""


class DownloadFailed(TaeError):
    """Fallo la descarga de una URL; `cause` la clasifica (spec §6)."""

    def __init__(
        self,
        message: str,
        *,
        cause: FailureCause = FailureCause.UNKNOWN,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause
        self.url = url
