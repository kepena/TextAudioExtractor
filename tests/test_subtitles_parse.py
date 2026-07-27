from tae.core.subtitles import parse_srt

SRT = """1
00:00:00,000 --> 00:00:02,000
Primera linea

2
00:00:02,500 --> 00:00:04,000
Segunda
con salto

3
00:00:04,000 --> 00:00:05,000
Tercera
"""


def test_parse_basic():
    segs = parse_srt(SRT)
    assert len(segs) == 3
    assert segs[0].start == 0.0
    assert segs[0].end == 2.0
    assert segs[0].text == "Primera linea"


def test_parse_joins_multiline_text():
    segs = parse_srt(SRT)
    assert segs[1].text == "Segunda con salto"


def test_parse_accepts_dot_millis():
    segs = parse_srt("1\n00:00:01.250 --> 00:00:02.000\nHola\n")
    assert len(segs) == 1
    assert segs[0].start == 1.25


def test_parse_empty_returns_empty():
    assert parse_srt("") == []
    assert parse_srt("basura sin tiempos") == []
