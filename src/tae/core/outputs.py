"""Render de Segment[] a los dos formatos de salida.

El .txt es el mismo contenido del .srt sin las marcas de tiempo (spec §5).
"""

from __future__ import annotations

from pathlib import Path

from .errors import OutputWriteError
from .models import Segment


def write_srt(segments: list[Segment], path: Path) -> Path:
    """Escribe un .srt estandar: bloques numerados con HH:MM:SS,mmm."""
    path = Path(path)
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    _write(path, "\n".join(lines).rstrip("\n") + "\n")
    return path


def write_txt(segments: list[Segment], path: Path) -> Path:
    """Escribe texto plano legible: una linea por segmento, sin marcas."""
    path = Path(path)
    body = "\n".join(seg.text.strip() for seg in segments if seg.text.strip())
    _write(path, body + ("\n" if body else ""))
    return path


def _fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = round(seconds * 1000)
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError(
            f"No pude escribir {path.name}. Revisa el espacio en disco y los permisos "
            f"de la carpeta de salida. ({exc})"
        ) from exc
