"""Inspeccion del video con ffprobe: duracion, audio y pistas de subtitulos."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import UnreadableVideo
from .ffmpeg_utils import ensure_ffmpeg, run
from .models import ProbeResult, SubtitleTrack


def probe(video: Path) -> ProbeResult:
    """Devuelve un ProbeResult o lanza UnreadableVideo si ffprobe no puede leerlo."""
    video = Path(video)
    if not video.exists():
        raise UnreadableVideo(f"El archivo no existe: {video}")

    paths = ensure_ffmpeg()
    result = run(
        [
            paths.ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-show_streams",
            "-of", "json",
            str(video),
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        detail = (result.stderr or "").strip()
        raise UnreadableVideo(
            "No pude leer este video, puede estar incompleto o en un formato no soportado. "
            f"{detail}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UnreadableVideo(f"ffprobe devolvio una respuesta invalida: {exc}") from exc

    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    subtitle_tracks: list[SubtitleTrack] = []
    sub_index = 0
    for s in streams:
        if s.get("codec_type") == "subtitle":
            tags = s.get("tags", {}) or {}
            subtitle_tracks.append(
                SubtitleTrack(
                    index=sub_index,
                    language=tags.get("language"),
                    codec=s.get("codec_name"),
                )
            )
            sub_index += 1

    duration = _extract_duration(data, streams)
    return ProbeResult(
        duration=duration,
        has_audio=has_audio,
        subtitle_tracks=subtitle_tracks,
    )


def _extract_duration(data: dict, streams: list[dict]) -> float:
    """Duracion desde format, con fallback al mayor stream."""
    fmt_dur = data.get("format", {}).get("duration")
    if fmt_dur:
        try:
            return float(fmt_dur)
        except (TypeError, ValueError):
            pass
    best = 0.0
    for s in streams:
        d = s.get("duration")
        if d:
            try:
                best = max(best, float(d))
            except (TypeError, ValueError):
                continue
    return best
