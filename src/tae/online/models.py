"""Estructuras de datos del modulo online.

Espejan a `core.models` pero para el flujo por URL: opciones de trabajo, resultado
de descarga, entradas de playlist y el resumen de lote. El texto final sigue
saliendo de `core.models.Segment`, asi que no se duplica nada de eso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tae.core.models import TextSource

from .errors import FailureCause


@dataclass
class OnlineJobOptions:
    """Lo que el usuario pide para una URL (desde CLI o GUI).

    Standalone en vez de componer sobre `core.JobOptions`: aquel exige un `video`
    local que aqui no existe. Reusa los mismos nombres de campo para que el mapeo
    sea obvio.
    """

    url: str
    out_dir: Path
    want_txt: bool = True
    want_srt: bool = True
    want_audio: bool = False
    force_transcribe: bool = False
    language: str | None = None       # None = idioma original del video
    model: str = "medium"             # tiny|base|small|medium|large-v3
    audio_format: str = "mp3"         # formato del audio entregado al usuario
    allow_auto_subs: bool = False     # aceptar subtitulos auto-generados (ASR)
    keep_video: bool = False          # conservar los temporales descargados
    cookies: str | None = None        # navegador (firefox/chrome/...) o ruta a cookies.txt (P8)

    @property
    def wants_text(self) -> bool:
        return self.want_txt or self.want_srt


@dataclass(frozen=True)
class DownloadResult:
    """Artefactos que yt-dlp dejo en disco para una URL."""

    audio_path: Path
    title: str
    video_id: str
    language: str | None = None
    subtitle_path: Path | None = None
    subtitle_is_auto: bool = False
    index: int | None = None          # posicion en la playlist, si aplica
    playlist_title: str | None = None


@dataclass(frozen=True)
class PlaylistEntry:
    """Una entrada de una playlist, sin descargar todavia (B3)."""

    url: str
    title: str
    video_id: str
    index: int


@dataclass(frozen=True)
class UrlInfo:
    """Resultado de inspeccionar una URL: video unico o playlist (B3)."""

    is_playlist: bool
    entries: list[PlaylistEntry]
    playlist_title: str | None = None


@dataclass
class OnlineJobResult:
    """Rutas generadas para una URL y como se obtuvo el texto (espeja JobResult)."""

    txt_path: Path | None = None
    srt_path: Path | None = None
    audio_path: Path | None = None
    text_source: TextSource = TextSource.NONE
    language: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class BatchFailure:
    """Un fallo de una entrada de lote, con su causa legible (spec §5.2, §6)."""

    url: str
    title: str | None
    cause: FailureCause
    message: str


@dataclass
class BatchReport:
    """Resumen de un lote: exitos y fallos, sin abortar el resto (spec §5.2)."""

    successes: list[OnlineJobResult] = field(default_factory=list)
    failures: list[BatchFailure] = field(default_factory=list)
    playlist_title: str | None = None

    @property
    def total(self) -> int:
        return len(self.successes) + len(self.failures)
