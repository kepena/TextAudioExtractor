"""Integracion ligera con media real sintetizada por ffmpeg (sin Whisper)."""

from pathlib import Path

import pytest

from tae.core import pipeline as pipeline_mod
from tae.core.audio import extract_audio
from tae.core.errors import NoAudioTrack
from tae.core.ffmpeg_utils import find_ffmpeg, run
from tae.core.models import (
    JobOptions,
    ProbeResult,
    Segment,
    SubtitleTrack,
    TextSource,
)
from tae.core.pipeline import run as run_pipeline
from tae.core.probe import probe

ffmpeg_missing = find_ffmpeg() is None
skip_no_ffmpeg = pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg no disponible")


def _make_video(path: Path, *, with_audio: bool) -> Path:
    paths = find_ffmpeg()
    cmd = [paths.ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    cmd += ["-shortest", str(path)]
    result = run(cmd)
    assert result.returncode == 0, result.stderr
    return path


@skip_no_ffmpeg
def test_probe_detecta_audio_y_duracion(tmp_path):
    video = _make_video(tmp_path / "v.mp4", with_audio=True)
    p = probe(video)
    assert p.has_audio is True
    assert p.duration == pytest.approx(1.0, abs=0.3)
    assert p.has_subtitles is False


@skip_no_ffmpeg
def test_probe_video_mudo(tmp_path):
    video = _make_video(tmp_path / "mudo.mp4", with_audio=False)
    p = probe(video)
    assert p.has_audio is False


@skip_no_ffmpeg
def test_extract_audio_genera_archivo(tmp_path):
    video = _make_video(tmp_path / "v.mp4", with_audio=True)
    out = extract_audio(video, tmp_path / "v.mp3")
    assert out.exists() and out.stat().st_size > 0


@skip_no_ffmpeg
def test_pipeline_solo_audio(tmp_path):
    video = _make_video(tmp_path / "clip.mp4", with_audio=True)
    opts = JobOptions(
        video=video,
        out_dir=tmp_path / "out",
        want_txt=False,
        want_srt=False,
        want_audio=True,
    )
    result = run_pipeline(opts)
    assert result.audio_path is not None
    assert result.audio_path.exists()
    assert result.txt_path is None


@skip_no_ffmpeg
def test_pipeline_audio_en_video_mudo_falla_claro(tmp_path):
    video = _make_video(tmp_path / "mudo.mp4", with_audio=False)
    opts = JobOptions(
        video=video,
        out_dir=tmp_path / "out",
        want_txt=False,
        want_srt=False,
        want_audio=True,
    )
    with pytest.raises(NoAudioTrack):
        run_pipeline(opts)


# --- Enrutado de diarizacion (sin ejecutar whisperx real: se monkeypatchea) ---


@skip_no_ffmpeg
def test_pipeline_diarize_enruta_a_diarize_no_a_transcribe(tmp_path, monkeypatch):
    """Con diarize=True se llama a diarize.transcribe_and_diarize, no a transcribe,
    y las salidas salen con etiqueta de hablante."""
    called = {"diarize": False, "transcribe": False}

    def fake_diarize(audio, **kw):
        called["diarize"] = True
        assert kw.get("num_speakers") == 2  # se propaga el nº de hablantes
        return [Segment(0.0, 1.0, "hola", speaker="SPEAKER_00")], "es"

    def fake_transcribe(audio, **kw):
        called["transcribe"] = True
        return [Segment(0.0, 1.0, "hola")], "es"

    monkeypatch.setattr(pipeline_mod.diarize, "transcribe_and_diarize", fake_diarize)
    monkeypatch.setattr(pipeline_mod.transcribe, "transcribe", fake_transcribe)
    # Fuerza el camino CPU sin importar si esta maquina tiene WSL2/GPU real
    # configurado (P11): el objetivo de este test es el arbol de decision.
    monkeypatch.setattr(pipeline_mod.diarize_wsl, "check_availability", lambda: (False, "test"))

    video = _make_video(tmp_path / "clip.mp4", with_audio=True)
    opts = JobOptions(
        video=video,
        out_dir=tmp_path / "out",
        want_txt=True,
        want_srt=True,
        want_audio=False,
        diarize=True,
        num_speakers=2,
    )
    result = run_pipeline(opts)
    assert called["diarize"] and not called["transcribe"]
    assert result.text_source == TextSource.TRANSCRIBED
    srt = result.srt_path.read_text(encoding="utf-8")
    assert "SPEAKER_00: hola" in srt


@skip_no_ffmpeg
def test_pipeline_diarize_sin_audio_falla_claro(tmp_path):
    """--diarize sobre un video sin audio da NoAudioTrack con mensaje de diarizar."""
    video = _make_video(tmp_path / "mudo.mp4", with_audio=False)
    opts = JobOptions(
        video=video,
        out_dir=tmp_path / "out",
        want_txt=True,
        want_srt=True,
        diarize=True,
    )
    with pytest.raises(NoAudioTrack) as exc:
        run_pipeline(opts)
    assert "diarizar" in str(exc.value).lower()


def test_obtain_text_diarize_ignora_subtitulos(tmp_path, monkeypatch):
    """Con subtitulos presentes + diarize, se ignora la rama embedded y se transcribe.

    Unit test puro del arbol de decision: no necesita ffmpeg, ni GPU, ni token.
    """
    def boom(*a, **k):  # extract_subtitles NO debe llamarse si diarize esta activo
        raise AssertionError("no debe usar la rama de subtitulos incrustados")

    monkeypatch.setattr(
        pipeline_mod.diarize,
        "transcribe_and_diarize",
        lambda audio, **kw: ([Segment(0.0, 1.0, "x", speaker="SPEAKER_00")], "es"),
    )
    monkeypatch.setattr(pipeline_mod.subtitles, "extract_subtitles", boom)
    monkeypatch.setattr(
        pipeline_mod.audio_mod, "extract_wav_for_whisper", lambda src, dst: dst
    )
    monkeypatch.setattr(pipeline_mod.diarize_wsl, "check_availability", lambda: (False, "test"))

    info_probe = ProbeResult(
        duration=1.0,
        has_audio=True,
        subtitle_tracks=[SubtitleTrack(index=0, language="es", codec="mov_text")],
    )
    opts = JobOptions(video=tmp_path / "x.mp4", out_dir=tmp_path, diarize=True)
    segments, source, language = pipeline_mod._obtain_text(
        opts, info_probe, lambda m: None, lambda m: None, None, None
    )
    assert source == TextSource.TRANSCRIBED
    assert segments[0].speaker == "SPEAKER_00"
