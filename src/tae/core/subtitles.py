"""Extraccion de subtitulos incrustados y parseo de .srt a Segment[].

ffmpeg convierte la pista de subtitulos elegida a un .srt temporal; luego se
parsea a la misma estructura Segment que usa la transcripcion.
"""

from __future__ import annotations

import html
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from .errors import SubtitleExtractionFailed
from .ffmpeg_utils import ensure_ffmpeg, run
from .models import Segment

_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)

# Tags inline de WebVTT: <c>, </c>, <c.colorCCCCCC>, <00:00:01.000>, <v Autor>...
_VTT_TAG_RE = re.compile(r"</?[^>]+>")


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
    return _parse_cues(content, _clean_srt_text)


def parse_vtt(content: str) -> list[Segment]:
    """Parsea texto en formato WebVTT a Segment[]. Tolerante y aditivo al SRT.

    WebVTT es casi SRT pero con cabecera `WEBVTT`, milisegundos con `.`, posibles
    *cue settings* tras el timestamp (`align:start position:0%`) y tags inline
    (`<c>`, `<00:00:01.000>`). Los bloques que no son cues (header, `NOTE`,
    `STYLE`, `REGION`) no traen linea de tiempo y se ignoran solos.
    """
    return _parse_cues(content, _clean_vtt_text)


def _parse_cues(content: str, clean: Callable[[str], str]) -> list[Segment]:
    """Motor comun de SRT/VTT. Un bloque puede traer MAS de un cue.

    Algunos WebVTT (p. ej. los "rolling captions" de TED) no separan cada cue con
    una linea en blanco: un mismo bloque acumula varias lineas de tiempo. Por eso
    se recorren TODAS las lineas `-->` del bloque, no solo la primera, y el texto
    de cada cue son las lineas hasta el siguiente timestamp. Ademas se descartan
    cues degenerados (texto vacio) y duplicados identicos consecutivos.
    """
    segments: list[Segment] = []
    blocks = re.split(r"\r?\n\r?\n+", content.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        time_idxs = [i for i, ln in enumerate(lines) if _TIME_RE.search(ln)]
        if not time_idxs:
            continue  # header WEBVTT, NOTE, STYLE, REGION o bloque sin timestamp
        for pos, ti in enumerate(time_idxs):
            m = _TIME_RE.search(lines[ti])
            if not m:
                continue
            start = _to_seconds(m.group(1), m.group(2), m.group(3), m.group(4))
            end = _to_seconds(m.group(5), m.group(6), m.group(7), m.group(8))
            end_idx = time_idxs[pos + 1] if pos + 1 < len(time_idxs) else len(lines)
            text_lines = lines[ti + 1 : end_idx]
            # Si sigue otro cue en el mismo bloque, la ultima linea puede ser el
            # indice numerico del cue siguiente (SRT mal formado): descartarla.
            if pos + 1 < len(time_idxs) and text_lines and text_lines[-1].strip().isdigit():
                text_lines = text_lines[:-1]
            text = clean(" ".join(text_lines))
            if not text:
                continue
            seg = Segment(start=start, end=end, text=text)
            if segments and _same_cue(segments[-1], seg):
                continue  # duplicado exacto consecutivo (captions "rolling")
            segments.append(seg)
    return segments


def _clean_srt_text(raw: str) -> str:
    """Colapsa espacios y recorta; el SRT no trae tags inline que limpiar."""
    return re.sub(r"\s+", " ", raw).strip()


def _clean_vtt_text(raw: str) -> str:
    """Quita tags inline de WebVTT, decodifica entidades HTML y colapsa espacios."""
    text = _VTT_TAG_RE.sub("", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _same_cue(a: Segment, b: Segment) -> bool:
    return a.start == b.start and a.end == b.end and a.text == b.text


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0
