"""CLI del motor. Subcomandos:

- `tae local <video>` — flujo local (extrae de un archivo de video).
- `tae url <URL>`     — flujo online (descarga de YouTube/plataformas via yt-dlp).

Cliente delgado sobre `core.pipeline` y `online.runner`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from .core.errors import TaeError
from .core.models import JobOptions
from .core.pipeline import run as run_pipeline

app = typer.Typer(add_completion=False, help="Extrae texto y audio de un video (local u online).")


# ---------- callbacks de consola compartidos ----------
def _on_stage(msg: str) -> None:
    typer.secho(f"→ {msg}", fg=typer.colors.CYAN)


def _on_info(msg: str) -> None:
    typer.secho(f"  {msg}", fg=typer.colors.BRIGHT_BLACK)


def _on_progress(fraction: float) -> None:
    pct = int(fraction * 100)
    print(f"\r  transcribiendo... {pct:3d}%", end="", flush=True)
    if fraction >= 1.0:
        print()


def _report_result(txt_path, srt_path, audio_path, language, source) -> None:
    typer.secho("\nListo. Archivos generados:", fg=typer.colors.GREEN)
    for label, path in (
        ("texto", txt_path),
        ("subtitulos", srt_path),
        ("audio", audio_path),
    ):
        if path:
            typer.echo(f"  {label}: {path}")
    if language:
        typer.echo(f"  idioma: {language} ({source})")


@app.command("local")
def local(
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
    """Procesa un VIDEO local y escribe las salidas pedidas."""
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

    try:
        result = run_pipeline(
            options, on_stage=_on_stage, on_progress=_on_progress, on_info=_on_info
        )
    except TaeError as exc:
        typer.secho(f"\nError: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    _report_result(
        result.txt_path, result.srt_path, result.audio_path,
        result.language, result.text_source.value,
    )


@app.command("url")
def url(
    link: str = typer.Argument(..., metavar="URL", help="URL de YouTube u otra plataforma."),
    txt: bool = typer.Option(True, "--txt/--no-txt", help="Generar texto plano .txt."),
    srt: bool = typer.Option(True, "--srt/--no-srt", help="Generar subtitulos .srt."),
    audio: bool = typer.Option(False, "--audio/--no-audio", help="Extraer el audio."),
    force_transcribe: bool = typer.Option(
        False, "--force-transcribe", help="Transcribir aunque el creador tenga subtitulos."
    ),
    allow_auto_subs: bool = typer.Option(
        False, "--allow-auto-subs",
        help="Aceptar subtitulos auto-generados (ASR) si no hay del creador.",
    ),
    lang: str | None = typer.Option(
        None, "--lang", help="Idioma (ej. es, en). Por defecto el original del video."
    ),
    model: str = typer.Option(
        "medium", "--model", help="Modelo Whisper: tiny|base|small|medium|large-v3."
    ),
    out: Path = typer.Option(
        Path("."), "--out", help="Carpeta de salida. Por defecto: la carpeta actual."
    ),
    audio_format: str = typer.Option(
        "mp3", "--audio-format", help="Formato del audio: mp3|m4a|wav|flac."
    ),
    keep_video: bool = typer.Option(
        False, "--keep-video", help="Conservar la fuente descargada junto a las salidas."
    ),
    cookies: str | None = typer.Option(
        None, "--cookies",
        help="Cookies para login/anti-bot (YouTube): nombre de navegador con sesion "
        "(firefox, chrome, edge) o ruta a un cookies.txt.",
    ),
) -> None:
    """Descarga una URL (video o playlist) y escribe las salidas pedidas."""
    # Import diferido: el modulo online no debe cargarse en el flujo local.
    from .online.download import probe_url
    from .online.models import OnlineJobOptions
    from .online.runner import run_playlist, run_url, summarize_batch
    from .online.ytdlp_utils import JS_RUNTIME_HINT, ensure_ytdlp, find_js_runtime

    if not (txt or srt or audio):
        typer.secho("No pediste ninguna salida (--txt/--srt/--audio).", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    opts = OnlineJobOptions(
        url=link,
        out_dir=out,
        want_txt=txt,
        want_srt=srt,
        want_audio=audio,
        force_transcribe=force_transcribe,
        language=lang,
        model=model,
        audio_format=audio_format,
        allow_auto_subs=allow_auto_subs,
        keep_video=keep_video,
        cookies=cookies,
    )

    try:
        ensure_ytdlp()
        if find_js_runtime() is None:
            _on_info(JS_RUNTIME_HINT)
        _on_stage("Inspeccionando la URL...")
        info = probe_url(link)
        if info.is_playlist:
            typer.secho(
                f"Playlist con {len(info.entries)} videos"
                + (f": {info.playlist_title}" if info.playlist_title else "")
                + ". Procesando en lote...",
                fg=typer.colors.CYAN,
            )

            def on_item(pos: int, total: int, title: str) -> None:
                typer.secho(f"\n[{pos}/{total}] {title}", fg=typer.colors.MAGENTA)

            report = run_playlist(
                opts,
                on_stage=_on_stage,
                on_info=_on_info,
                on_progress=_on_progress,
                on_item=on_item,
            )
            typer.secho("\n" + summarize_batch(report), fg=typer.colors.GREEN)
            if report.failures and not report.successes:
                raise typer.Exit(code=1)
            return

        result = run_url(
            opts, on_stage=_on_stage, on_info=_on_info, on_progress=_on_progress
        )
    except TaeError as exc:  # incluye DownloadFailed
        typer.secho(f"\nError: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    _report_result(
        result.txt_path, result.srt_path, result.audio_path,
        result.language, result.text_source.value,
    )


if __name__ == "__main__":
    app()
    sys.exit(0)
