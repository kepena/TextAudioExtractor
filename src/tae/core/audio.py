"""Extraccion de audio con ffmpeg.

Dos usos:
- `extract_audio`: el audio "para el usuario" (mp3/otro), como salida entregable.
- `extract_wav_for_whisper`: un wav 16kHz mono temporal que faster-whisper consume.
"""

from __future__ import annotations

from pathlib import Path

from .errors import NoAudioTrack, TaeError
from .ffmpeg_utils import ensure_ffmpeg, run


def extract_audio(video: Path, out_path: Path, *, audio_format: str = "mp3") -> Path:
    """Extrae la pista de audio a un archivo entregable. Lanza NoAudioTrack si no hay."""
    paths = ensure_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    codec = _codec_for(audio_format)
    result = run(
        [
            paths.ffmpeg, "-y",
            "-i", str(video),
            "-vn",              # sin video
            *codec,
            str(out_path),
        ]
    )
    if result.returncode != 0:
        _raise_audio_error(result.stderr, "extraer el audio")
    return out_path


def extract_wav_for_whisper(video: Path, out_path: Path) -> Path:
    """Extrae un wav 16kHz mono (lo que Whisper espera) a un archivo temporal."""
    paths = ensure_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = run(
        [
            paths.ffmpeg, "-y",
            "-i", str(video),
            "-vn",
            "-ac", "1",         # mono
            "-ar", "16000",     # 16 kHz
            "-c:a", "pcm_s16le",
            str(out_path),
        ]
    )
    if result.returncode != 0:
        _raise_audio_error(result.stderr, "preparar el audio para transcribir")
    return out_path


def _codec_for(audio_format: str) -> list[str]:
    fmt = audio_format.lower()
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if fmt in ("m4a", "aac"):
        return ["-c:a", "aac", "-b:a", "192k"]
    if fmt == "wav":
        return ["-c:a", "pcm_s16le"]
    if fmt == "flac":
        return ["-c:a", "flac"]
    # por defecto, dejar que ffmpeg elija por la extension
    return []


def _raise_audio_error(stderr: str | None, what: str) -> None:
    text = (stderr or "").lower()
    if "does not contain any stream" in text or "output file #0 does not contain" in text:
        raise NoAudioTrack(
            "El video no tiene pista de audio: no hay nada que extraer ni transcribir."
        )
    raise TaeError(f"No pude {what}. {(stderr or '').strip()}")
