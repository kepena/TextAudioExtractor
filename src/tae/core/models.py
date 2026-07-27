"""Estructuras de datos compartidas por todo el motor.

La pieza central es `Segment`: tanto la extraccion de subtitulos como la
transcripcion producen la misma lista de segmentos, y de ahi salen el .srt y el
.txt (spec §5). Asi no hay codigo duplicado para los dos formatos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True)
class Segment:
    """Un bloque de texto con su intervalo de tiempo, en segundos."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SubtitleTrack:
    """Una pista de subtitulos incrustada detectada por ffprobe."""

    index: int
    language: str | None
    codec: str | None


@dataclass(frozen=True)
class ProbeResult:
    """Lo que sabemos del video tras inspeccionarlo con ffprobe."""

    duration: float
    has_audio: bool
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)

    @property
    def has_subtitles(self) -> bool:
        return len(self.subtitle_tracks) > 0


class TextSource(StrEnum):
    """De donde salio el texto final."""

    EMBEDDED = "embedded"      # extraido de una pista de subtitulos
    TRANSCRIBED = "transcribed"  # generado por Whisper
    NONE = "none"              # no se genero texto (solo audio)


@dataclass
class JobOptions:
    """Todo lo que el usuario pide para un video (desde CLI o GUI)."""

    video: Path
    out_dir: Path
    want_txt: bool = True
    want_srt: bool = True
    want_audio: bool = False
    force_transcribe: bool = False
    language: str | None = None       # None = autodeteccion
    model: str = "medium"             # tiny|base|small|medium|large-v3
    audio_format: str = "mp3"         # formato del audio entregado al usuario

    @property
    def wants_text(self) -> bool:
        return self.want_txt or self.want_srt


@dataclass
class JobResult:
    """Rutas generadas y como se obtuvo el texto."""

    txt_path: Path | None = None
    srt_path: Path | None = None
    audio_path: Path | None = None
    text_source: TextSource = TextSource.NONE
    language: str | None = None
