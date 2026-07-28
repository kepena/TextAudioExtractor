"""Orquestador: de un video + opciones a los archivos de salida.

Decide entre extraer subtitulos o transcribir, genera el audio si se pide, y
escribe .txt/.srt. Reporta etapas y progreso, y respeta la cancelacion.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from . import audio as audio_mod
from . import diarize, outputs, subtitles, transcribe
from .errors import Cancelled, NoAudioTrack, SubtitleExtractionFailed
from .ffmpeg_utils import ensure_ffmpeg
from .models import JobOptions, JobResult, ProbeResult, Segment, TextSource
from .probe import probe as probe_video

StageCb = Callable[[str], None]
ProgressCb = Callable[[float], None]
CancelCb = Callable[[], bool]


def run(
    options: JobOptions,
    *,
    on_stage: StageCb | None = None,
    on_progress: ProgressCb | None = None,
    on_info: StageCb | None = None,
    should_cancel: CancelCb | None = None,
) -> JobResult:
    def stage(msg: str) -> None:
        if on_stage:
            on_stage(msg)

    def info(msg: str) -> None:
        if on_info:
            on_info(msg)

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise Cancelled("Trabajo cancelado por el usuario.")

    ensure_ffmpeg()
    video = Path(options.video)
    out_dir = Path(options.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / video.stem

    stage("Inspeccionando el video...")
    info_probe: ProbeResult = probe_video(video)
    check_cancel()

    result = JobResult()

    # --- Texto: extraer subtitulos o transcribir ---
    if options.wants_text:
        segments, source, language = _obtain_text(
            options, info_probe, stage, info, on_progress, should_cancel
        )
        result.text_source = source
        result.language = language
        check_cancel()
        if options.want_srt:
            stage("Escribiendo .srt...")
            result.srt_path = outputs.write_srt(segments, base.with_suffix(".srt"))
        if options.want_txt:
            stage("Escribiendo .txt...")
            result.txt_path = outputs.write_txt(segments, base.with_suffix(".txt"))

    # --- Audio separado ---
    if options.want_audio:
        check_cancel()
        if not info_probe.has_audio:
            raise NoAudioTrack("El video no tiene pista de audio: no hay audio que extraer.")
        stage("Extrayendo el audio...")
        audio_out = base.with_suffix("." + options.audio_format)
        result.audio_path = audio_mod.extract_audio(
            video, audio_out, audio_format=options.audio_format
        )

    return result


def _obtain_text(
    options: JobOptions,
    info_probe: ProbeResult,
    stage: StageCb,
    info: StageCb,
    on_progress: ProgressCb | None,
    should_cancel: CancelCb | None,
) -> tuple[list[Segment], TextSource, str | None]:
    """Devuelve (segmentos, fuente, idioma) segun subtitulos vs transcripcion."""
    # --diarize fuerza transcribir el audio: los subtitulos no traen identidad de
    # voz (spec §5), asi que se ignoran aunque existan.
    use_embedded = (
        info_probe.has_subtitles
        and not options.force_transcribe
        and not options.diarize
    )

    if options.diarize and info_probe.has_subtitles:
        info(
            "Ignoro los subtitulos incrustados: para identificar hablantes "
            "transcribo el audio."
        )

    if use_embedded:
        stage("Extrayendo los subtitulos incrustados...")
        try:
            segments = subtitles.extract_subtitles(options.video, track_index=0)
            language = info_probe.subtitle_tracks[0].language
            return segments, TextSource.EMBEDDED, language
        except SubtitleExtractionFailed as exc:
            if not info_probe.has_audio:
                raise
            info(
                f"No pude usar los subtitulos incrustados ({exc}). "
                "Transcribo el audio en su lugar."
            )
            # cae a transcripcion

    # Transcripcion
    if not info_probe.has_audio:
        if options.diarize:
            raise NoAudioTrack("El video no tiene pista de audio: no hay audio que diarizar.")
        raise NoAudioTrack(
            "El video no tiene subtitulos ni pista de audio: no hay texto que generar."
        )

    with tempfile.TemporaryDirectory() as tmp:
        stage("Extrayendo el audio para transcribir...")
        wav = audio_mod.extract_wav_for_whisper(options.video, Path(tmp) / "audio.wav")
        if options.diarize:
            stage("Transcribiendo e identificando hablantes...")
            segments, language = diarize.transcribe_and_diarize(
                wav,
                model=options.model,
                language=options.language,
                num_speakers=options.num_speakers,
                duration=info_probe.duration,
                on_progress=on_progress,
                on_info=info,
                should_cancel=should_cancel,
            )
        else:
            stage("Transcribiendo...")
            segments, language = transcribe.transcribe(
                wav,
                model=options.model,
                language=options.language,
                duration=info_probe.duration,
                on_progress=on_progress,
                on_info=info,
                should_cancel=should_cancel,
            )
    return segments, TextSource.TRANSCRIBED, language
