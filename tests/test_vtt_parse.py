"""Parseo de WebVTT a Segment[] (B1), sin romper el parser SRT existente."""

from tae.core.subtitles import parse_srt, parse_vtt

VTT = """WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:04.000 align:start position:0%
<c>Hola</c> mundo

00:00:04.500 --> 00:00:07.250
Segunda&nbsp;linea con <00:00:05.000><c> tags</c> inline

NOTE esto es un comentario que debe ignorarse

00:00:08.000 --> 00:00:10.000
Tercera linea
"""


def test_parse_vtt_extrae_segmentos_limpios():
    segs = parse_vtt(VTT)
    assert len(segs) == 3
    assert segs[0].start == 1.0
    assert segs[0].end == 4.0
    assert segs[0].text == "Hola mundo"  # tags <c> removidos
    # entidad HTML decodificada y tags de tiempo inline removidos
    assert segs[1].text == "Segunda linea con tags inline"
    assert segs[2].text == "Tercera linea"


def test_parse_vtt_ignora_header_y_notes():
    segs = parse_vtt(VTT)
    # El header WEBVTT y el bloque NOTE no producen segmentos.
    textos = [s.text for s in segs]
    assert not any("WEBVTT" in t for t in textos)
    assert not any("comentario" in t for t in textos)


def test_parse_vtt_vacio_devuelve_lista_vacia():
    assert parse_vtt("WEBVTT\n\n") == []
    assert parse_vtt("") == []


def test_parser_srt_sigue_intacto():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHola\n"
    segs = parse_srt(srt)
    assert len(segs) == 1
    assert segs[0].text == "Hola"


# VTT estilo TED: cues sin linea en blanco entre ellos dentro del mismo bloque.
# El primero es un cue degenerado (0.000->0.001) cuyo "texto" es un espacio
# no-rompible, seguido pegado del cue real; y mas abajo, dos cues identicos
# consecutivos (rolling captions). El parser ingenuo colaba el segundo timestamp
# como texto y duplicaba lineas.
TED_VTT = (
    "WEBVTT\n\n"
    "00:00:00.000 --> 00:00:00.001\n"
    " \n"
    "00:00:02.103 --> 00:00:04.678\n"
    "Good morning. How are you?\n\n"
    "00:00:28.491 --> 00:00:30.904\n"
    "in all of the presentations\n"
    "00:00:28.491 --> 00:00:30.904\n"
    "in all of the presentations\n"
)


def test_parse_vtt_cues_pegados_sin_linea_en_blanco():
    segs = parse_vtt(TED_VTT)
    # El cue degenerado se descarta y el duplicado se colapsa: 2 segmentos.
    assert len(segs) == 2
    assert segs[0].start == 2.103
    assert segs[0].text == "Good morning. How are you?"
    assert segs[1].start == 28.491
    assert segs[1].text == "in all of the presentations"


def test_parse_vtt_no_filtra_timestamps_en_el_texto():
    # Ningun timestamp debe colarse como texto de un cue.
    for seg in parse_vtt(TED_VTT):
        assert "-->" not in seg.text
    # Y el cue degenerado de 1 ms no debe aparecer.
    assert all(seg.start != 0.0 for seg in parse_vtt(TED_VTT))
