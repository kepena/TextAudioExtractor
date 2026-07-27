"""Integracion ligera con media real sintetizada por ffmpeg (sin Whisper)."""

from pathlib import Path

import pytest

from tae.core.audio import extract_audio
from tae.core.errors import NoAudioTrack
from tae.core.ffmpeg_utils import find_ffmpeg, run
from tae.core.models import JobOptions
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
