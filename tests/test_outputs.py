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


# --- Diarizacion: segmentos con hablante (spec §5) ---
SEG_SPK = [
    Segment(0.0, 2.0, "Cuentame como te sentiste.", speaker="SPEAKER_00"),
    Segment(2.0, 4.0, "Con ansiedad al principio.", speaker="SPEAKER_01"),
    Segment(4.0, 5.0, "Y luego?", speaker="SPEAKER_00"),
    Segment(5.0, 6.0, "Fue bajando.", speaker="SPEAKER_00"),
]


def test_write_srt_con_hablante(tmp_path):
    """Cada bloque .srt prefija el texto con el hablante."""
    content = write_srt(SEG_SPK, tmp_path / "s.srt").read_text(encoding="utf-8")
    assert "SPEAKER_00: Cuentame como te sentiste." in content
    assert "SPEAKER_01: Con ansiedad al principio." in content


def test_write_txt_con_hablante_y_linea_en_blanco_al_cambiar(tmp_path):
    """El .txt prefija por hablante y separa con linea en blanco solo al cambiar."""
    content = write_txt(SEG_SPK, tmp_path / "s.txt").read_text(encoding="utf-8")
    lines = content.split("\n")
    assert lines[0] == "SPEAKER_00: Cuentame como te sentiste."
    assert lines[1] == ""  # cambia a SPEAKER_01
    assert lines[2] == "SPEAKER_01: Con ansiedad al principio."
    assert lines[3] == ""  # cambia de vuelta a SPEAKER_00
    assert lines[4] == "SPEAKER_00: Y luego?"
    # dos intervenciones seguidas del mismo hablante: sin linea en blanco entre ellas
    assert lines[5] == "SPEAKER_00: Fue bajando."


def test_salida_sin_hablante_no_cambia(tmp_path):
    """Sin speaker, .srt/.txt quedan byte a byte como sin diarizar (candado)."""
    plain = [Segment(s.start, s.end, s.text) for s in SEG_SPK]  # mismos textos, sin speaker
    srt = write_srt(plain, tmp_path / "p.srt").read_text(encoding="utf-8")
    txt = write_txt(plain, tmp_path / "p.txt").read_text(encoding="utf-8")
    assert "SPEAKER_" not in srt
    assert "SPEAKER_" not in txt
    # el .txt sin hablante es una linea por segmento, sin lineas en blanco intercaladas
    assert txt.split("\n") == [
        "Cuentame como te sentiste.",
        "Con ansiedad al principio.",
        "Y luego?",
        "Fue bajando.",
        "",
    ]
