from tae.core.models import Segment
from tae.core.outputs import _fmt_ts, write_srt, write_txt

SEGMENTS = [
    Segment(0.0, 1.5, "Hola mundo"),
    Segment(1.5, 3.25, "Segunda linea"),
    Segment(3.25, 3900.123, "Tercera"),
]


def test_fmt_ts_basic():
    assert _fmt_ts(0) == "00:00:00,000"
    assert _fmt_ts(1.5) == "00:00:01,500"
    assert _fmt_ts(3661.007) == "01:01:01,007"


def test_fmt_ts_never_negative():
    assert _fmt_ts(-5) == "00:00:00,000"


def test_write_srt(tmp_path):
    path = write_srt(SEGMENTS, tmp_path / "out.srt")
    content = path.read_text(encoding="utf-8")
    assert "1\n00:00:00,000 --> 00:00:01,500\nHola mundo" in content
    assert "2\n00:00:01,500 --> 00:00:03,250\nSegunda linea" in content
    # tres bloques numerados
    assert content.count(" --> ") == 3


def test_write_txt_has_no_timestamps(tmp_path):
    path = write_txt(SEGMENTS, tmp_path / "out.txt")
    content = path.read_text(encoding="utf-8")
    assert "-->" not in content
    assert content.splitlines() == ["Hola mundo", "Segunda linea", "Tercera"]


def test_txt_is_srt_without_marks(tmp_path):
    """El .txt debe ser el contenido del .srt sin marcas (spec §5)."""
    srt = write_srt(SEGMENTS, tmp_path / "a.srt").read_text(encoding="utf-8")
    txt = write_txt(SEGMENTS, tmp_path / "a.txt").read_text(encoding="utf-8")
    for seg in SEGMENTS:
        assert seg.text in srt
        assert seg.text in txt
