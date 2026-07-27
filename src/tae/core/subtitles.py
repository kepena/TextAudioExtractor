"""Extraccion de subtitulos incrustados y parseo de .srt a Segment[].

ffmpeg convierte la pista de subtitulos elegida a un .srt temporal; luego se
parsea a la misma estructura Segment que usa la transcripcion.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .errors import SubtitleExtractionFailed
from .ffmpeg_utils import ensure_ffmpeg, run
from .models import Segment

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def extract_subtitles(video: Path, track_index: int = 0) -> list[Segment]:
    """Extrae la pista `track_index` a srt y la parsea. Lanza SubtitleExtractionFailed."""
    paths = ensure_ffmpeg()
    video = Path(video)

    with tempfile.TemporaryDirectory() as tmp:
        srt_path = Path(tmp) / "track.srt"
        result = run(
            [
                paths.ffmpeg, "-y",
                "-i", str(video),
                "-map", f"0:s:{track_index}",
                "-c:s", "srt",
                str(srt_path),
            ]
        )
        if result.returncode != 0 or not srt_path.exists():
            raise SubtitleExtractionFailed(
                f"No pude extraer la pista de subtitulos {track_index}. "
                f"{(result.stderr or '').strip()}"
            )
        content = srt_path.read_text(encoding="utf-8", errors="replace")

    segments = parse_srt(content)
    if not segments:
        raise SubtitleExtractionFailed(
            "La pista de subtitulos se extrajo vacia o en un formato que no pude leer."
        )
    return segments


def parse_srt(content: str) -> list[Segment]:
    """Parsea texto en formato SRT a una lista de Segment. Tolerante a ruido."""
    segments: list[Segment] = []
    blocks = re.split(r"\r?\n\r?\n+", content.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        time_line_idx = _find_time_line(lines)
        if time_line_idx is None:
            continue
        m = _TIME_RE.search(lines[time_line_idx])
        if not m:
            continue
        start = _to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
        end = _to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
        text = " ".join(lines[time_line_idx + 1 :]).strip()
        if text:
            segments.append(Segment(start=start, end=end, text=text))
    return segments


def _find_time_line(lines: list[str]) -> int | None:
    for i, ln in enumerate(lines):
        if _TIME_RE.search(ln):
            return i
    return None


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0
