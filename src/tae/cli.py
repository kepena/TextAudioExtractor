"""CLI del motor: `tae <video> [flags]`. Es un cliente delgado sobre pipeline.run."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .core.errors import TaeError
from .core.models import JobOptions
from .core.pipeline import run as run_pipeline

app = typer.Typer(add_completion=False, help="Extrae texto y audio de un video.")


@app.command()
def main(
    video: Path = typer.Argument(..., exists=True, dir_okay=False, help="Ruta del video."),
    txt: bool = typer.Option(True, "--txt/--no-txt", help="Generar texto plano .txt."),
    srt: bool = typer.Option(True, "--srt/--no-srt", help="Generar subtitulos .srt."),
    audio: bool = typer.Option(False, "--audio/--no-audio", help="Extraer el audio."),
    force_transcribe: bool = typer.Option(
        False, "--force-transcribe", help="Transcribir aunque haya subtitulos incrustados."
    ),
    lang: str | None = typer.Option(
        None, "--lang", help="Idioma (ej. es, en). Por defecto autodeteccion."
    ),
    model: str = typer.Option(
        "medium", "--model", help="Modelo Whisper: tiny|base|small|medium|large-v3."
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Carpeta de salida. Por defecto: <carpeta del video>/<nombre>."
    ),
    audio_format: str = typer.Option(
        "mp3", "--audio-format", help="Formato del audio: mp3|m4a|wav|flac."
    ),
) -> None:
    """Procesa VIDEO y escribe las salidas pedidas."""
    if not (txt or srt or audio):
        typer.secho("No pediste ninguna salida (--txt/--srt/--audio).", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    out_dir = out if out is not None else video.parent / video.stem

    options = JobOptions(
        video=video,
        out_dir=out_dir,
        want_txt=txt,
        want_srt=srt,
        want_audio=audio,
        force_transcribe=force_transcribe,
        language=lang,
        model=model,
        audio_format=audio_format,
    )

    def on_stage(msg: str) -> None:
        typer.secho(f"→ {msg}", fg=typer.colors.CYAN)

    def on_info(msg: str) -> None:
        typer.secho(f"  {msg}", fg=typer.colors.BRIGHT_BLACK)

    def on_progress(fraction: float) -> None:
        pct = int(fraction * 100)
        print(f"\r  transcribiendo... {pct:3d}%", end="", flush=True)
        if fraction >= 1.0:
            print()

    try:
        result = run_pipeline(
            options, on_stage=on_stage, on_progress=on_progress, on_info=on_info
        )
    except TaeError as exc:
        typer.secho(f"\nError: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho("\nListo. Archivos generados:", fg=typer.colors.GREEN)
    for label, path in (
        ("texto", result.txt_path),
        ("subtitulos", result.srt_path),
        ("audio", result.audio_path),
    ):
        if path:
            typer.echo(f"  {label}: {path}")
    if result.language:
        typer.echo(f"  idioma: {result.language} ({result.text_source.value})")


if __name__ == "__main__":
    app()
    sys.exit(0)
