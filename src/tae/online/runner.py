"""Orquestacion online: de una URL (o playlist) a los archivos de salida.

Espeja `core.pipeline` pero sobre artefactos descargados por yt-dlp: decide entre
subtitulos del creador o transcripcion, entrega el audio en el formato pedido y,
en lote, captura los fallos por entrada sin abortar el resto (spec §5.2).
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from tae.core import audio as core_audio
from tae.core import outputs, subtitles, transcribe
from tae.core.ffmpeg_utils import ensure_ffmpeg
from tae.core.models import Segment, TextSource

from . import naming
from .download import download, probe_url
from .errors import DownloadFailed, FailureCause, message_for
from .models import (
    BatchFailure,
    BatchReport,
    DownloadResult,
    OnlineJobOptions,
    OnlineJobResult,
)
from .ytdlp_utils import ensure_ytdlp

StageCb = Callable[[str], None]
ProgressCb = Callable[[float], None]
CancelCb = Callable[[], bool]


def run_url(
    opts: OnlineJobOptions,
    *,
    on_stage: StageCb | None = None,
    on_info: StageCb | None = None,
    on_progress: ProgressCb | None = None,
    should_cancel: CancelCb | None = None,
    out_stem: str | None = None,
) -> OnlineJobResult:
    """Procesa una sola URL de video y escribe las salidas pedidas (C1).

    `out_stem` permite que el runner de lote imponga el nombre (con prefijo `NN_`
    y colisiones resueltas); si es None, se deriva del titulo del video.
    """
    def stage(msg: str) -> None:
        if on_stage:
            on_stage(msg)

    def info(msg: str) -> None:
        if on_info:
            on_info(msg)

    def check_cancel() -> None:
        from tae.core.errors import Cancelled

        if should_cancel and should_cancel():
            raise Cancelled("Trabajo cancelado por el usuario.")

    ensure_ytdlp()
    ensure_ffmpeg()

    tmp = Path(tempfile.mkdtemp(prefix="tae_online_"))
    try:
        stage("Descargando la fuente...")
        dl = download(
            opts.url,
            tmp,
            lang=opts.language,
            allow_auto_subs=opts.allow_auto_subs,
            keep_video=opts.keep_video,
            cookies=opts.cookies,
        )
        check_cancel()

        stem = out_stem or naming.safe_stem(dl.title)
        out_dir = Path(opts.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        base = out_dir / stem

        result = OnlineJobResult(title=dl.title)

        if opts.wants_text:
            segments, source, language = _obtain_text(
                opts, dl, tmp, stage, info, on_progress, should_cancel
            )
            result.text_source = source
            result.language = language
            check_cancel()
            if opts.want_srt:
                stage("Escribiendo .srt...")
                result.srt_path = outputs.write_srt(segments, base.with_suffix(".srt"))
            if opts.want_txt:
                stage("Escribiendo .txt...")
                result.txt_path = outputs.write_txt(segments, base.with_suffix(".txt"))

        if opts.want_audio:
            check_cancel()
            stage("Preparando el audio...")
            audio_out = base.with_suffix("." + opts.audio_format)
            result.audio_path = core_audio.extract_audio(
                dl.audio_path, audio_out, audio_format=opts.audio_format
            )

        if opts.keep_video and dl.audio_path.exists():
            kept = out_dir / f"{stem}_fuente{dl.audio_path.suffix}"
            shutil.move(str(dl.audio_path), str(kept))

        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_playlist(
    opts: OnlineJobOptions,
    *,
    on_stage: StageCb | None = None,
    on_info: StageCb | None = None,
    on_progress: ProgressCb | None = None,
    on_item: Callable[[int, int, str], None] | None = None,
    should_cancel: CancelCb | None = None,
) -> BatchReport:
    """Expande la playlist y procesa cada entrada; captura fallos sin abortar (C2).

    Nombres de salida: prefijo `NN_` segun el orden de la playlist, con sufijos
    `_2`, `_3` ante colision de titulo (spec §5.2). `on_item(i, total, titulo)`
    avisa el avance por entrada.
    """
    def info(msg: str) -> None:
        if on_info:
            on_info(msg)

    url_info = probe_url(opts.url, cookies=opts.cookies)
    entries = url_info.entries
    report = BatchReport(playlist_title=url_info.playlist_title)

    used_stems: set[str] = set()
    total = len(entries)
    width = max(2, len(str(total)))

    for pos, entry in enumerate(entries, start=1):
        if should_cancel and should_cancel():
            from tae.core.errors import Cancelled

            raise Cancelled("Lote cancelado por el usuario.")

        if on_item:
            on_item(pos, total, entry.title)

        stem = naming.numbered(
            pos, naming.resolve_collisions(naming.safe_stem(entry.title), used_stems),
            width=width,
        )
        entry_opts = OnlineJobOptions(
            url=entry.url,
            out_dir=opts.out_dir,
            want_txt=opts.want_txt,
            want_srt=opts.want_srt,
            want_audio=opts.want_audio,
            force_transcribe=opts.force_transcribe,
            language=opts.language,
            model=opts.model,
            audio_format=opts.audio_format,
            allow_auto_subs=opts.allow_auto_subs,
            keep_video=opts.keep_video,
            cookies=opts.cookies,
        )
        try:
            res = run_url(
                entry_opts,
                on_stage=on_stage,
                on_info=on_info,
                on_progress=on_progress,
                should_cancel=should_cancel,
                out_stem=stem,
            )
            report.successes.append(res)
        except DownloadFailed as exc:
            info(f"Fallo '{entry.title}': {exc}")
            report.failures.append(
                BatchFailure(
                    url=entry.url,
                    title=entry.title,
                    cause=exc.cause,
                    message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - un video no debe tumbar el lote
            info(f"Fallo '{entry.title}': {exc}")
            report.failures.append(
                BatchFailure(
                    url=entry.url,
                    title=entry.title,
                    cause=FailureCause.UNKNOWN,
                    message=str(exc),
                )
            )

    return report


def _obtain_text(
    opts: OnlineJobOptions,
    dl: DownloadResult,
    tmp: Path,
    stage: StageCb,
    info: StageCb,
    on_progress: ProgressCb | None,
    should_cancel: CancelCb | None,
) -> tuple[list[Segment], TextSource, str | None]:
    """Devuelve (segmentos, fuente, idioma): subtitulos del creador vs Whisper."""
    use_sub = dl.subtitle_path is not None and not opts.force_transcribe

    if use_sub and dl.subtitle_path is not None:
        origen = "auto-generados" if dl.subtitle_is_auto else "del creador"
        stage(f"Usando los subtitulos {origen}...")
        content = dl.subtitle_path.read_text(encoding="utf-8", errors="replace")
        if dl.subtitle_path.suffix.lower() == ".vtt":
            segments = subtitles.parse_vtt(content)
        else:
            segments = subtitles.parse_srt(content)
        if segments:
            return segments, TextSource.EMBEDDED, dl.language
        info("El subtitulo venia vacio o ilegible; transcribo el audio.")

    stage("Preparando el audio para transcribir...")
    wav = core_audio.extract_wav_for_whisper(dl.audio_path, tmp / "whisper.wav")
    stage("Transcribiendo...")
    segments, language = transcribe.transcribe(
        wav,
        model=opts.model,
        language=opts.language,
        on_progress=on_progress,
        on_info=info,
        should_cancel=should_cancel,
    )
    return segments, TextSource.TRANSCRIBED, language


def summarize_batch(report: BatchReport) -> str:
    """Texto legible del resumen de lote para la CLI (exitos/fallos con causa)."""
    lines = [
        f"Lote terminado: {len(report.successes)} ok, {len(report.failures)} con fallo "
        f"(de {report.total}).",
    ]
    if report.failures:
        lines.append("Fallos:")
        for f in report.failures:
            title = f.title or f.url
            lines.append(f"  - {title}: {message_for(f.cause)}")
    return "\n".join(lines)
